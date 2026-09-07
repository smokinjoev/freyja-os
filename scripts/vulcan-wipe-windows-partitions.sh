#!/usr/bin/env bash
set -euo pipefail

if [[ "${CONFIRM_VULCAN_WINDOWS_WIPE:-}" != "YES" ]]; then
  echo "Refusing to run: set CONFIRM_VULCAN_WINDOWS_WIPE=YES." >&2
  exit 2
fi

if [[ "${EUID}" -ne 0 ]]; then
  echo "Refusing to run: this script must be run as root via sudo." >&2
  exit 2
fi

host="$(hostname)"
if [[ "${host}" != "Vulcan" && "${host}" != "vulcan" && "${host}" != vulcan.* ]]; then
  echo "Refusing to run: expected host Vulcan, got ${host}." >&2
  exit 2
fi

disk="/dev/nvme0n1"
efi="${disk}p1"
msr="${disk}p2"
windows="${disk}p3"
recovery="${disk}p4"
linux_root="${disk}p5"

root_source="$(findmnt -no SOURCE /)"
if [[ "${root_source}" != "${linux_root}" ]]; then
  echo "Refusing to run: expected / on ${linux_root}, got ${root_source}." >&2
  exit 2
fi

if [[ "$(findmnt -no SOURCE /boot/efi)" != "${efi}" ]]; then
  echo "Refusing to run: expected /boot/efi on ${efi}." >&2
  exit 2
fi

if [[ "$(lsblk -no FSTYPE "${windows}")" != "ntfs" ]]; then
  echo "Refusing to run: ${windows} is not NTFS." >&2
  exit 2
fi

if [[ "$(lsblk -no FSTYPE "${recovery}")" != "ntfs" ]]; then
  echo "Refusing to run: ${recovery} is not NTFS." >&2
  exit 2
fi

if [[ "$(lsblk -no FSTYPE "${linux_root}")" != "ext4" ]]; then
  echo "Refusing to run: ${linux_root} is not ext4." >&2
  exit 2
fi

if pgrep -af "ollama pull qwen3.5:122b-a10b" >/dev/null; then
  echo "Stopping active qwen3.5:122b-a10b pull before partition changes."
  pkill -f "ollama pull qwen3.5:122b-a10b" || true
fi

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup_dir="/root/freyja-backups/${timestamp}-before-windows-wipe"
mkdir -p "${backup_dir}"

sgdisk --backup="${backup_dir}/nvme0n1.gpt" "${disk}"
efibootmgr -v > "${backup_dir}/efibootmgr-before.txt" || true
lsblk -f > "${backup_dir}/lsblk-before.txt"
parted -s "${disk}" unit s print > "${backup_dir}/parted-before.txt"

echo "Setting Ubuntu first in EFI boot order."
efibootmgr -o 0000,0002 || true

echo "Deleting Windows partitions: ${msr}, ${windows}, ${recovery}."
sgdisk --delete=2 --delete=3 --delete=4 "${disk}"
partprobe "${disk}" || true
udevadm settle

echo "Creating Linux data partition in freed former Windows space."
sgdisk --new=2:0:0 --typecode=2:8300 --change-name=2:"Freyja Models" "${disk}"
partprobe "${disk}" || true
udevadm settle

data_partition="${disk}p2"
mkfs.ext4 -F -L FREYJA_MODELS "${data_partition}"

mkdir -p /srv/freyja-models
uuid="$(blkid -s UUID -o value "${data_partition}")"
if ! grep -q "${uuid}" /etc/fstab; then
  printf 'UUID=%s /srv/freyja-models ext4 defaults,noatime 0 2\n' "${uuid}" >> /etc/fstab
fi
mount /srv/freyja-models

efibootmgr -v > "${backup_dir}/efibootmgr-after.txt" || true
lsblk -f > "${backup_dir}/lsblk-after.txt"
parted -s "${disk}" unit s print > "${backup_dir}/parted-after.txt"

mkdir -p /home/joe/.freyja/backups
cp -a "${backup_dir}" "/home/joe/.freyja/backups/"
chown -R joe:joe "/home/joe/.freyja/backups/$(basename "${backup_dir}")" || true

echo "Done."
echo "Backup: ${backup_dir}"
echo "Data partition mounted at /srv/freyja-models"
