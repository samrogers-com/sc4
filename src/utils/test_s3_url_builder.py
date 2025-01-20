#!/usr/bin/env python3

from s3_url_builder import construct_image_url

# Test cases for construct_image_url
base_url = construct_image_url(
    app="ns-cards",
    image_type="sets",
    category="star_wars",
    sub_category="sw-galaxy",
    image_name="sw_galaxy_1_base101-p03.jpg"
)
print("Constructed URL:", base_url)
# Output: https://samscollectibles.s3-us-west-1.amazonaws.com/ns-cards/sets/star_wars/sw-galaxy-1/sw_galaxy_1_base101-p03.jpg