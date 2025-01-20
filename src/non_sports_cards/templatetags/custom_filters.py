# src/non_sports_cards/templatetags/custom_filters.py

from django import template
from ..models import NonSportsCards

register = template.Library()

@register.filter
def get_manufacturers_list(_):
    return NonSportsCards.MANUFACTURERS  

@register.filter
def filter_by_manufacturer(queryset, manufacturer):
    """Filters a queryset of NonSportsCards by manufacturer."""
    return queryset.filter(manufacturer=manufacturer)

