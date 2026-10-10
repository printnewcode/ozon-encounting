from pathlib import Path

from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.core.exceptions import ValidationError


VALID_UPLOAD_EXTENSIONS = {'.xlsx', '.xls', '.csv'}


class SuperuserAuthenticationForm(AuthenticationForm):
    error_messages = {
        'invalid_login': 'Неверный логин или пароль администратора.',
        'inactive': 'Неверный логин или пароль администратора.',
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].label = 'Логин'
        self.fields['username'].widget.attrs.update({
            'class': 'form-control',
            'autocomplete': 'username',
            'placeholder': 'Логин администратора',
        })
        self.fields['username'].error_messages['required'] = 'Введите логин.'
        self.fields['password'].label = 'Пароль'
        self.fields['password'].widget.attrs.update({
            'class': 'form-control',
            'autocomplete': 'current-password',
            'placeholder': 'Введите пароль',
        })
        self.fields['password'].error_messages['required'] = 'Введите пароль.'

    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if not user.is_superuser:
            raise ValidationError(self.error_messages['invalid_login'], code='invalid_login')


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


class SalesReportPeriodForm(forms.Form):
    date_from = forms.DateField(
        label='Дата с',
        required=False,
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
    )
    date_to = forms.DateField(
        label='Дата по',
        required=False,
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
    )

    def clean(self):
        cleaned_data = super().clean()
        date_from = cleaned_data.get('date_from')
        date_to = cleaned_data.get('date_to')

        if date_from and date_to and date_from > date_to:
            raise ValidationError('Дата начала периода не может быть позже даты окончания.')

        return cleaned_data


class CostPriceImportForm(forms.Form):
    file = forms.FileField(
        label='Файл с названиями и себестоимостью',
        help_text='Два столбца: название товара и себестоимость. Поддерживаются .xlsx и .csv.',
        widget=forms.FileInput(attrs={'accept': '.xlsx,.csv'}),
    )

    def clean_file(self):
        uploaded_file = self.cleaned_data['file']
        extension = Path(uploaded_file.name).suffix.lower()
        if extension not in {'.xlsx', '.csv'}:
            raise ValidationError('Поддерживаются только файлы .xlsx и .csv.')
        if uploaded_file.size > 5 * 1024 * 1024:
            raise ValidationError('Размер файла не должен превышать 5 МБ.')
        return uploaded_file
