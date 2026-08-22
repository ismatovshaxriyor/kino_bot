from tortoise import models, fields


class ChannelJoinRequest(models.Model):
    """Foydalanuvchi yopiq kanal/guruhga qo'shilish so'rovini yuborgani —
    admin hali tasdiqlamagan bo'lsa ham, botdan foydalanishga ruxsat berish
    uchun ishlatiladi ("chat_join_request" Telegram hodisasi orqali yoziladi)."""
    id = fields.IntField(pk=True)
    channel = fields.ForeignKeyField('models.Channels', related_name='join_requests')
    telegram_id = fields.BigIntField()
    requested_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        unique_together = ('channel', 'telegram_id')
