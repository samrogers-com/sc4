from django.conf import settings


def construct_image_url(app, image_type, category, sub_category, image_name):
    """
    Dynamically construct the S3/R2 URL for a card image.
    """
    base_url = getattr(settings, 'IMAGE_BASE_URL', '')
    return f"{base_url}{app}/{image_type}/{category}/{sub_category}/{image_name}"
