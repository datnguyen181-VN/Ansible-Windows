#!/usr/bin/env python3
"""
Ansible Windows Automation Framework - Inventory Generator
------------------------------------------------------------
Script đọc dữ liệu từ file CSV (mặc định: list_Server_windows.csv)
và tự động sinh ra cấu trúc inventory dành riêng cho WINDOWS TARGETS:
  1. inventory/hosts.ini (Chứa danh sách tất cả Windows server)
  2. inventory/group_vars/all.yml
  3. inventory/host_vars/<filename_key>.yml (Chứa biến kết nối WinRM)
"""

import csv
import os
import sys
import yaml

# Khai báo ánh xạ các cột CSV đặc thù sang biến tiêu chuẩn của Ansible
# Chốt: Cột 'user_id' trong CSV sẽ là tài khoản remote 'ansible_user'
COLUMN_MAPPING = {
    "ip_current": "ansible_host",
    "user_id": "ansible_user",
    "password": "ansible_password",
}


def get_ip_suffix(ip_address: str) -> str:
    """Get 3 numbers from the end of IP (VD: 192.168.1.112 -> 112)."""
    ip_str = ip_address.strip()
    if "." in ip_str:
        last_octet = ip_str.split(".")[-1]
        return last_octet.zfill(3) if len(last_octet) < 3 else last_octet
    return "000"


def ensure_directories_exist(base_dir: str = "inventory") -> None:
    """Tạo cấu trúc thư mục inventory/ nếu chưa tồn tại."""
    for subdir in ["group_vars", "host_vars"]:
        dir_path = os.path.join(base_dir, subdir)
        os.makedirs(dir_path, exist_ok=True)


def clean_inventory_files(inventory_dir: str = "inventory") -> None:
    """Xóa tất cả các file cấu hình cũ trước khi thực hiện xử lý mới."""
    print("[*] Ưu tiên dọn dẹp toàn bộ dữ liệu inventory cũ...")

    # 1. Xóa tất cả file trong host_vars
    host_vars_dir = os.path.join(inventory_dir, "host_vars")
    if os.path.exists(host_vars_dir):
        for filename in os.listdir(host_vars_dir):
            if filename.endswith(".yml") or filename.endswith(".yaml"):
                file_to_remove = os.path.join(host_vars_dir, filename)
                os.remove(file_to_remove)
                print(f"  [-] Đã xóa file host_vars cũ: {filename}")

    # 2. Xóa tất cả các file .ini cũ trong thư mục inventory/
    if os.path.exists(inventory_dir):
        for filename in os.listdir(inventory_dir):
            if filename.endswith(".ini"):
                file_to_remove = os.path.join(inventory_dir, filename)
                os.remove(file_to_remove)
                print(f"  [-] Đã xóa file cũ: {filename}")


def read_csv(csv_filepath: str) -> list[dict]:
    """
    Đọc file CSV và xử lý logic tên file & hostname:
    - Chuẩn hóa header và dữ liệu.
    - Giữ nguyên nội dung 'hostname' từ CSV.
    - Nếu hostname trùng nhau hoặc bị thiếu, sinh ra 'filename_key' có ghép 3 số cuối IP
      để đặt tên file mà KHÔNG làm thay đổi nội dung cột 'hostname' gốc.
    """
    if not os.path.exists(csv_filepath):
        print(f"[ERROR] File '{csv_filepath}' không tồn tại.")
        sys.exit(1)

    raw_hosts = []
    has_validation_error = False

    with open(csv_filepath, mode="r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row_index, row in enumerate(reader, start=2):
            cleaned_row = {}
            for k, v in row.items():
                if k is not None:
                    clean_k = " ".join(k.strip().split()).lower()
                    clean_v = " ".join(v.strip().split()) if v else ""
                    cleaned_row[clean_k] = clean_v

            ip_curr = cleaned_row.get("ip_current") or cleaned_row.get("ansible_host")

            if ip_curr:
                ip_new = cleaned_row.get("ip_new", "")
                gateway = cleaned_row.get("gateway", "")
                subnet_mask = cleaned_row.get("subnet_mask", "")

                if ip_new:
                    missing_fields = []
                    if not gateway:
                        missing_fields.append("gateway")
                    if not subnet_mask:
                        missing_fields.append("subnet_mask")

                    if missing_fields:
                        missing_str = ", ".join(missing_fields)
                        hostname_info = cleaned_row.get("hostname") or ip_curr
                        print(
                            f"[ERROR] Line {row_index} ({hostname_info}): 'ip_new' is provided ({ip_new}), "
                            f"but missing required field(s): {missing_str}. "
                            f"Please provide all required network settings."
                        )
                        has_validation_error = True

                raw_hosts.append(cleaned_row)

    if has_validation_error:
        print("\n[FAILED] Process aborted due to missing network configurations.")
        sys.exit(1)

    if not raw_hosts:
        print(f"[WARNING] File '{csv_filepath}' không chứa dữ liệu hợp lệ.")
        return []

    # 1. Đếm số lần xuất hiện của từng hostname
    hostname_counts = {}
    for row in raw_hosts:
        hn = row.get("hostname", "").strip()
        if hn:
            hostname_counts[hn] = hostname_counts.get(hn, 0) + 1

    # 2. Xử lý định danh tên file (filename_key) và giữ nguyên hostname nội dung
    processed_hosts = []
    for row in raw_hosts:
        raw_hn = row.get("hostname", "").strip()
        ip_curr = row.get("ip_current") or row.get("ansible_host", "")
        ip_suffix = get_ip_suffix(ip_curr)

        # Tính toán tên file (filename_key)
        if not raw_hn:
            filename_key = f"win-server-{ip_suffix}"
            row["hostname"] = raw_hn if raw_hn else filename_key
        elif hostname_counts.get(raw_hn, 0) > 1:
            filename_key = f"{raw_hn}-{ip_suffix}"
            row["hostname"] = raw_hn
        else:
            filename_key = raw_hn
            row["hostname"] = raw_hn

        row["filename_key"] = filename_key
        processed_hosts.append(row)

    return processed_hosts


def write_yaml(filepath: str, data: dict) -> None:
    """Ghi dữ liệu dictionary ra file YAML định dạng UTF-8."""
    with open(filepath, mode="w", encoding="utf-8") as f:
        yaml.dump(
            data, f, default_flow_style=False, allow_unicode=True, sort_keys=False
        )


def generate_hosts(
    hosts_data: list[dict], base_dir: str = "inventory"
) -> None:
    """
    Sinh ra duy nhất 1 file inventory/hosts.ini chứa tất cả thông tin Windows server.
    """
    ini_filename = "hosts.ini"
    ini_path = os.path.join(base_dir, ini_filename)

    with open(ini_path, mode="w", encoding="utf-8") as f:
        f.write("[windows_servers]\n")
        for row in hosts_data:
            filename_key = row["filename_key"]
            ip = row.get("ip_current") or row.get("ansible_host", "")
            f.write(f"{filename_key} ansible_host={ip}\n")
        f.write("\n")

    print(f"  [+] Đã tạo file inventory duy nhất: {ini_filename}")


def generate_group_vars(
    output_path: str = "inventory/group_vars/all.yml",
) -> None:
    """Sinh file group_vars/all.yml chứa các biến cấu hình mặc định chung cho Windows."""
    default_vars = {
        "reboot_after_update": False,
    }
    write_yaml(output_path, default_vars)


def generate_host_vars(
    hosts_data: list[dict], host_vars_dir: str = "inventory/host_vars"
) -> None:
    """
    Sinh các file host_vars/<filename_key>.yml dành riêng cho Windows (WinRM).
    Tự động gắn user_id (mặc định Administrator nếu trống).
    """
    for row in hosts_data:
        filename_key = row["filename_key"]
        host_vars = {}

        for key, value in row.items():
            # Bỏ qua các key nội bộ
            if key in ["os", "filename_key"]:
                continue

            # Nối key theo mapping hoặc giữ nguyên tên cột
            if key in COLUMN_MAPPING:
                ansible_var = COLUMN_MAPPING[key]
                host_vars[ansible_var] = value
            else:
                host_vars[key] = value

        # =========================================================
        # CHỐT LOGIC ANSIBLE_USER & CẤU HÌNH WINRM CHO WINDOWS
        # =========================================================
        # 1. Kiểm tra user_id: Nếu trống/không có trong CSV -> Fallback thành "Administrator"
        current_user = host_vars.get("ansible_user", "").strip()
        if not current_user:
            host_vars["ansible_user"] = "Administrator"

        # 2. Các biến kết nối WinRM chuẩn cho Windows
        host_vars["ansible_connection"] = "winrm"
        host_vars["ansible_port"] = 5985  # Mặc định HTTPS (Cổng 5985)
        host_vars["ansible_winrm_server_cert_validation"] = "ignore"
        host_vars["ansible_winrm_transport"] = "ntlm"

        host_file = os.path.join(host_vars_dir, f"{filename_key}.yml")
        write_yaml(host_file, host_vars)
        print(f"  [+] Đã tạo file host_vars (Windows): host_vars/{filename_key}.yml (User: {host_vars['ansible_user']})")


def main() -> None:
    if len(sys.argv) > 1:
        csv_file = sys.argv[1]
    elif os.path.exists("infoserver.csv"):
        csv_file = "infoserver.csv"
    elif os.path.exists("1.csv"):
        csv_file = "1.csv"
    else:
        print("[ERROR] Không tìm thấy file CSV đầu vào (infoserver.csv / 1.csv).")
        sys.exit(1)

    print(f"[*] Bắt đầu xử lý file: {csv_file}")

    # 1. Tạo thư mục cấu trúc nếu chưa có
    ensure_directories_exist("inventory")

    # 2. Xóa sạch các file inventory cũ
    clean_inventory_files("inventory")

    print("-" * 50)

    # 3. Đọc CSV & Kiểm tra tính hợp lệ của dữ liệu
    hosts_data = read_csv(csv_file)

    # 4. Sinh lại các file cấu hình mới
    generate_hosts(hosts_data, "inventory")
    generate_group_vars("inventory/group_vars/all.yml")
    generate_host_vars(hosts_data, "inventory/host_vars")

    print(f"\n[SUCCESS] Đã đồng bộ thành công inventory Windows cho {len(hosts_data)} host(s)!")


if __name__ == "__main__":
    main()