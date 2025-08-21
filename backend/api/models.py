from django.db import models


class Car_list(models.Model):
    brand = models.CharField(max_length=30, verbose_name='Бренд', default='')
    model = models.CharField(max_length=30, verbose_name='Модель', default='')
    engine = models.CharField(max_length=30, verbose_name='Двигатель', default='')
    price_usd = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='Цена (USD)', default=0)
    price_byn = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='Цена (BYN)', default=0)
    description = models.TextField(blank=True, verbose_name='Описание', default='')
    image = models.ImageField(upload_to='images/', blank=True, null=True, verbose_name='Изображение', default=None)

    class Meta:
        verbose_name = 'Автомобиль'
        verbose_name_plural = 'Автомобили'
        ordering = ['brand', 'model']



    def __str__(self):
        return f'{self.brand} | {self.model} | {self.engine} | {self.price_usd} USD | {self.price_byn} BYN'