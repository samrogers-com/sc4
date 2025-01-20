# file: src/utils/s3_url_builder.py

def construct_image_url(app, image_type, category, sub_category, image_name):
    """
    Construct the full S3 URL for an image.

    :param app: The app name, e.g., 'ns-cards'
    :param image_type: The type of image, e.g., 'sets', 'boxes'
    :param category: The category of the item, e.g., 'Marvel'
    :param sub_category: The sub-category, e.g., 'Superheroes'
    :param image_name: The name of the image file, e.g., 'image.jpg'
    :return: Full S3 URL as a string.
    """
    base_url = "https://samscollectibles.s3.amazonaws.com"
    return f"{base_url}/{app}/{image_type}/{category}/{sub_category}/{image_name}"
