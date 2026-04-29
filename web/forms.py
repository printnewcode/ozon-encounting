from pathlib import Path

from django import forms
from django.core.exceptions import ValidationError


VALID_UPLOAD_EXTENSIONS = {'.xlsx', '.xls', '.csv'}


def validate_file_extension(value) -> None:
    extension = Path(value.name).suffix.lower()
    if extension not in VALID_UPLOAD_EXTENSIONS:
        raise ValidationError(
            'Неподдерживаемый формат файла. Пожалуйста, загрузите .xlsx, .xls или .csv.'
        )


class SupplyUploadForm(forms.Form):
    file = forms.FileField(
        label='Файл с поставкой',
        validators=[validate_file_extension],
        widget=forms.FileInput(attrs={'class': 'form-control', 'accept': '.xlsx,.xls,.csv'}),
    )


class SalesUploadForm(forms.Form):
    SALE_TYPE_CHOICES = (
        ('ozon', 'Продажа Ozon'),
        ('free', 'Свободная продажа'),
    )

    sale_type = forms.ChoiceField(
        choices=SALE_TYPE_CHOICES,
        label='Тип продажи',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    file = forms.FileField(
        label='Файл с продажами',
        validators=[validate_file_extension],
        widget=forms.FileInput(attrs={'class': 'form-control', 'accept': '.xlsx,.xls,.csv'}),
    )
