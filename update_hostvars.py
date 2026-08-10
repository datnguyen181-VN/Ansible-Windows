import os
import re
import glob

HOST_VARS_DIR = "/root/ansible-os-automation/inventory/host_vars"

def is_valid_value(val):
    """
    Kiểm tra giá trị có hợp lệ hay không.
    Trả về False nếu giá trị bị rỗng, None, null, ~
    """
    if val is None:
        return False
    cleaned = str(val).strip().strip("'\"").strip()
    if not cleaned or cleaned.lower() in ['null', 'none', '~', '']:
        return False
    return True

def clean_val(val):
    return str(val).strip().strip("'\"").strip()

def update_host_var_file(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Tìm chính xác giá trị của các key trên CÙNG MỘT DÒNG (không match xuống dòng dưới)
    user_match = re.search(r'^[ \t]*ansible_user:[ \t]*(.*)$', content, re.MULTILINE)
    ip_new_match = re.search(r'^[ \t]*ip_new:[ \t]*(.*)$', content, re.MULTILINE)
    pass_new_match = re.search(r'^[ \t]*password_new:[ \t]*(.*)$', content, re.MULTILINE)

    # Kiểm tra user admin
    is_admin = False
    if user_match and is_valid_value(user_match.group(1)):
        user_val = clean_val(user_match.group(1))
        if user_val.lower() in ['administrator', 'admin']:
            is_admin = True

    updated_ip = False
    updated_pass = False

    # 1. Cập nhật IP: CHỈ THỰC HIỆN KHI ip_new CÓ GIÁ TRỊ HỢP LỆ
    if ip_new_match and is_valid_value(ip_new_match.group(1)):
        ip_val = clean_val(ip_new_match.group(1))
        
        # Nếu ansible_host đã tồn tại -> ghi đè đúng dòng đó
        if re.search(r'^[ \t]*ansible_host:', content, re.MULTILINE):
            content = re.sub(r'^[ \t]*ansible_host:.*$', f'ansible_host: {ip_val}', content, flags=re.MULTILINE)
        # Nếu chưa có -> chèn ngay sau dòng ip_new
        else:
            content = re.sub(r'^(.*ip_new:.*)$', f'\\1\nansible_host: {ip_val}', content, flags=re.MULTILINE)
        updated_ip = True

    # 2. Cập nhật Password: CHỈ THỰC HIỆN KHI là admin VÀ password_new CÓ GIÁ TRỊ HỢP LỆ
    if is_admin and pass_new_match and is_valid_value(pass_new_match.group(1)):
        pass_val = clean_val(pass_new_match.group(1))
        
        # Nếu ansible_password đã tồn tại -> ghi đè đúng dòng đó
        if re.search(r'^[ \t]*ansible_password:', content, re.MULTILINE):
            content = re.sub(r'^[ \t]*ansible_password:.*$', f"ansible_password: '{pass_val}'", content, flags=re.MULTILINE)
        # Nếu chưa có -> chèn ngay sau dòng password_new
        else:
            content = re.sub(r'^(.*password_new:.*)$', f"\\1\nansible_password: '{pass_val}'", content, flags=re.MULTILINE)
        updated_pass = True

    # Ghi lại file nếu có thay đổi
    if updated_ip or updated_pass:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        status = []
        if updated_ip: status.append("ansible_host")
        if updated_pass: status.append("ansible_password")
        print(f"[OK] {os.path.basename(file_path)} -> Updated ({', '.join(status)})")
    else:
        print(f"[SKIP] {os.path.basename(file_path)} -> No valid ip_new or password_new to update")

def main():
    yaml_files = glob.glob(os.path.join(HOST_VARS_DIR, "*.yml")) + glob.glob(os.path.join(HOST_VARS_DIR, "*.yaml"))
    if not yaml_files:
        print(f"No YAML files found in {HOST_VARS_DIR}")
        return

    print("--- Start Updating Windows HOST_VARS ---")
    for file_path in sorted(yaml_files):
        update_host_var_file(file_path)

if __name__ == "__main__":
    main()