from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models.functions import Lower


class User(AbstractUser):
    """The site's user model (D-027).

    It exists from the first migration because Django cannot swap user models afterwards. Fields
    are added only when a phase needs them.
    """

    # Required, and unique regardless of case: Google sign-in (Phase 12) matches an existing staff
    # account by email, so two accounts must never differ only in letter case.
    email = models.EmailField("email address")

    class Meta(AbstractUser.Meta):
        constraints = [
            models.UniqueConstraint(Lower("email"), name="accounts_user_email_ci_unique"),
        ]
