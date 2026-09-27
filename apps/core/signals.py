from django.core.files.storage import default_storage
from django.db import transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver

from apps.core.media import asset_file_names
from apps.core.models import MediaAsset


@receiver(post_delete, sender=MediaAsset)
def delete_asset_files(sender, instance, **kwargs):
    """Remove an asset's master and variant files once its row is gone.

    Runs after commit, so a rolled-back delete never loses files. A signal rather than a delete()
    override, because QuerySet.delete() (admin bulk deletes) never calls delete().
    """
    names = asset_file_names(instance)

    def remove():
        for name in names:
            try:
                default_storage.delete(name)
            except OSError:
                pass

    transaction.on_commit(remove)
