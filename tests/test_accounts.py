import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from apps.accounts.models import User


def test_custom_user_model_is_active():
    assert settings.AUTH_USER_MODEL == "accounts.User"
    assert get_user_model() is User


@pytest.mark.django_db
def test_email_is_unique_regardless_of_case():
    User.objects.create_user(username="first", email="person@example.com")
    with pytest.raises(IntegrityError):
        User.objects.create_user(username="second", email="Person@Example.COM")


@pytest.mark.django_db
def test_email_is_required():
    user = User(username="nobody", email="")
    user.set_unusable_password()
    with pytest.raises(ValidationError) as excinfo:
        user.full_clean()
    assert "email" in excinfo.value.message_dict
