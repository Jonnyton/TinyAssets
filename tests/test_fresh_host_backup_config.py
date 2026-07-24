from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def test_fresh_host_backup_configuration_matches_root_run_service():
    template = (REPO / "deploy" / "tinyassets-env.template").read_text(
        encoding="utf-8"
    )
    deploy_runbook = (REPO / "deploy" / "DEPLOY.md").read_text(encoding="utf-8")
    cutover_runbook = (REPO / "docs" / "ops" / "day-of-cutover.md").read_text(
        encoding="utf-8"
    )
    backup_runbook = (
        REPO / "docs" / "ops" / "backup-restore-runbook.md"
    ).read_text(encoding="utf-8")
    backup_unit = (REPO / "deploy" / "tinyassets-backup.service").read_text(
        encoding="utf-8"
    )

    assert "\nBACKUP_DEST=\n" in f"\n{template}"
    assert "STORAGEBOX_HOST=" not in template
    assert "STORAGEBOX_USER=" not in template
    assert "STORAGEBOX_PASS=" not in template
    assert "sudo rclone config" in template

    assert "BACKUP_DEST=storagebox:tinyassets-backups" in deploy_runbook
    assert "sudo rclone config" in deploy_runbook
    assert "STORAGEBOX_" not in deploy_runbook

    assert "BACKUP_DEST=storagebox:tinyassets-backups" in cutover_runbook
    assert "/root/.config/rclone/rclone.conf" in cutover_runbook
    assert "/etc/tinyassets/backup/rclone.conf" not in cutover_runbook

    assert "/root/.config/rclone/rclone.conf" in backup_runbook
    assert "/app/.config/rclone/rclone.conf" not in backup_runbook
    assert "HOME=/app" not in backup_runbook
    assert backup_runbook.count("sudo rclone config create") == 2
    assert "sudo rclone lsd $BACKUP_DEST" in backup_runbook

    assert "destination credentials live in root's rclone configuration" in (
        backup_unit
    )
    assert "/root/.config/rclone/" in backup_unit
    assert "reads STORAGEBOX_*" not in backup_unit
    assert "rclone config written to $HOME is wiped" not in backup_unit
