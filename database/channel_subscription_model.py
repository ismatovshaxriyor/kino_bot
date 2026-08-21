from tortoise import models, fields


class ChannelSubscription(models.Model):
    """Foydalanuvchi biror kanalga a'zoligi bot orqali (obuna tekshiruvida)
    tasdiqlangan har bir hodisani belgilaydi — kanal bo'yicha "bot orqali
    qo'shilgan obunachilar" statistikasi shu yerdan hisoblanadi."""
    id = fields.IntField(pk=True)
    channel = fields.ForeignKeyField('models.Channels', related_name='subscriptions')
    telegram_id = fields.BigIntField()
    confirmed_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        unique_together = ('channel', 'telegram_id')
