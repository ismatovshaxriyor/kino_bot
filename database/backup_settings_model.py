from tortoise import fields, models


class BackupSettings(models.Model):
    """Avtomatik zaxira sozlamalari — bitta qatorli (singleton) jadval."""
    id = fields.IntField(pk=True)
    enabled = fields.BooleanField(default=True)
    interval_hours = fields.IntField(default=6)

    class Meta:
        table = "backup_settings"

    @classmethod
    async def get_settings(cls) -> "BackupSettings":
        settings, _ = await cls.get_or_create(id=1)
        return settings
