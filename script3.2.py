# Script untuk dijalankan di Server B, mengambil data dari Server A (Versi Akses Langsung /var/tmp)

import paramiko
import os
import traceback
from datetime import datetime, timedelta

# --- (WAJIB DIUBAH) Detail koneksi ke SERVER A ---
SERVER_IP = "192.168.111.134" # IP Server A (Sumber Data)
SERVER_PORT = 22
USERNAME = "xriczx"
PASSWORD = "xriczx555" 

# --- Path di Server A ---
TESTING_DIR = "/root/testing" 
# DIUBAH: Langsung menggunakan /var/tmp sebagai penampungan
REMOTE_TEMP_DIR = "/root/var/tmp" 

# --- Path di LOKAL Server B ---
LOCAL_BACKUP_BASE_DIR = "/home/subscribe/backups"

# --- Inisialisasi Klien ---
ssh_client = paramiko.SSHClient()
ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
sftp_client = None
files_to_archive = [] # Definisikan di luar try untuk bisa diakses di finally

# --- Fungsi helper untuk menjalankan command di server A ---
def execute_command(command):
    """Menjalankan perintah di server A dan menangani error."""
    print(f"▶️  Menjalankan di server A: {command}")
    stdin, stdout, stderr = ssh_client.exec_command(command, get_pty=True)
    exit_status = stdout.channel.recv_exit_status()
    
    error_output = stderr.read().decode().strip()
    if exit_status != 0:
        raise Exception(f"Error menjalankan '{command}': {error_output}")
        
    print(f"✅ Perintah di server A berhasil.")
    return stdout.read().decode().strip()

try:
    # 1. Login ke Server A
    print(f"Menghubungkan ke server A ({SERVER_IP})...")
    ssh_client.connect(hostname=SERVER_IP, port=SERVER_PORT, username=USERNAME, password=PASSWORD)
    print("✅ Koneksi SSH ke server A berhasil!")

    sftp_client = ssh_client.open_sftp()
    print("✅ Sesi SFTP berhasil dibuka.")

    # 2. Dapatkan daftar file yang akan diarsipkan dari Server A
    command_ls = f"sudo ls -ltrh {TESTING_DIR}"
    output_ls = execute_command(command_ls)

    today = datetime.now().date()
    yesterday = today - timedelta(days=1)
    
    file_dates = []
    month_map = {name: num for num, name in enumerate(['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'], 1)}

    for line in output_ls.splitlines():
        if not line.startswith('-'): continue
        parts = line.split()
        if len(parts) < 9: continue
        try:
            file_date = datetime(today.year, month_map[parts[5]], int(parts[6])).date()
            if file_date != today and file_date != yesterday:
                files_to_archive.append(parts[8])
                file_dates.append(file_date)
        except (ValueError, KeyError): continue

    if not files_to_archive:
        print("\nℹ️  Tidak ada file yang perlu diarsipkan hari ini. Selesai.")
    else:
        print(f"\n ditemukan {len(files_to_archive)} file untuk diarsipkan: {files_to_archive}")

        # LANGKAH 1: Salin file dari /root/testing ke /var/tmp di Server A
        for filename in files_to_archive:
            source_path = f"{TESTING_DIR}/{filename}"
            execute_command(f"sudo cp {source_path} {REMOTE_TEMP_DIR}/")
        print(f"✅ File berhasil disalin ke {REMOTE_TEMP_DIR} di Server A.")
        
        # LANGKAH 2: Buat folder backup di LOKAL Server B
        min_date = min(file_dates)
        max_date = max(file_dates)
        folder_name = f"{min_date.day}-{max_date.day}-{today.strftime('%B').lower()}"
        local_new_backup_dir = os.path.join(LOCAL_BACKUP_BASE_DIR, folder_name)
        os.makedirs(local_new_backup_dir, exist_ok=True)
        print(f"✅ Folder lokal di Server B dibuat: {local_new_backup_dir}")

        # LANGKAH 3: UNDUH file dari Server A ke LOKAL Server B
        for filename in files_to_archive:
            remote_temp_path = f"{REMOTE_TEMP_DIR}/{filename}"
            local_destination_path = os.path.join(local_new_backup_dir, filename)
            
            print(f"📥 Mengunduh {filename} ke Server B...")
            sftp_client.get(remote_temp_path, local_destination_path)
        print("✅ Semua file berhasil diunduh ke Server B.")
        
        # LANGKAH 4: HAPUS file dari folder ASLI di Server A
        for filename in files_to_archive:
            remote_original_path = f"{TESTING_DIR}/{filename}"
            execute_command(f"sudo rm {remote_original_path}")
        print("✅ Semua file asli berhasil dihapus dari Server A.")

        print(f"\n🎉 Proses arsip berhasil! File diunduh ke: {local_new_backup_dir}")

except Exception as e:
    print(f"\n❌ TERJADI KESALAHAN KRITIS: {e}")
    print("--- LAPORAN DEBUG LENGKAP ---")
    traceback.print_exc()

finally:
    # DIUBAH: Membersihkan file individual, bukan seluruh folder
    if ssh_client.get_transport() and ssh_client.get_transport().is_active() and files_to_archive:
        print(f"🧹 Membersihkan file sementara di Server A dari: {REMOTE_TEMP_DIR}")
        for filename in files_to_archive:
            remote_temp_path = f"{REMOTE_TEMP_DIR}/{filename}"
            try:
                # Menghapus file yang tadi kita salin
                execute_command(f"sudo rm {remote_temp_path}")
            except Exception as clean_e:
                print(f"⚠️ Gagal membersihkan file {remote_temp_path}: {clean_e}")
    
    # LANGKAH 5: Tutup semua koneksi
    if sftp_client:
        sftp_client.close()
    if ssh_client.get_transport() and ssh_client.get_transport().is_active():
        print("\nMenutup koneksi SSH...")
        ssh_client.close()
