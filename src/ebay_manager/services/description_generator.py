"""
Auto-generate eBay HTML listing descriptions from product data.

Uses the Sam's Collectibles branded template (dark denim background,
sky blue headers, amber accents) to generate a complete eBay-compatible
HTML description when no pre-built file exists.

The generated HTML follows the same 5-section structure as the
pre-built files in ebay_uploads/:
    1. HEADER — title, highlights, collector line
    2. DESCRIPTION — product details, "What you get" bullets
    3. CONDITION — factory sealed / condition notes
    4. SHIPPING — standard combine shipping text
    5. FEEDBACK — satisfaction guarantee

Standard shipping text (approved by Sam):
    "Shipped with care using USPS Ground Advantage with tracking.
    Item will be packaged securely to prevent damage during transit
    and to ensure safe arrival. We offer combine shipping. Please
    message us before checkout if you are purchasing multiple items
    so we can provide a combined shipping invoice."
"""


def generate_description(title, specs=None, product_type='boxes'):
    """Generate a complete eBay HTML description from product data.

    Args:
        title: Listing title (e.g. "1996 Topps Star Wars 3Di Widevision Sealed Box")
        specs: Dict of item specifics (Manufacturer, Franchise, Set, Year, etc.)
        product_type: 'boxes', 'sets', 'packs', etc.

    Returns:
        Complete HTML string ready for eBay description field.
    """
    specs = specs or {}

    def _str(value, default=''):
        """Item specifics are stored as lists (eBay aspect format) — coerce
        to a single string, joining multiple values with a comma."""
        if value is None or value == '':
            return default
        if isinstance(value, (list, tuple)):
            if not value:
                return default
            return ', '.join(str(v) for v in value if v)
        return str(value)

    manufacturer = _str(specs.get('Manufacturer'))
    franchise = _str(specs.get('Franchise'))
    set_name = _str(specs.get('Set'))
    year = _str(specs.get('Year Manufactured'))
    genre = _str(specs.get('Genre'))
    movie = _str(specs.get('Movie'))
    tv_show = _str(specs.get('TV Show'))
    config = _str(specs.get('Configuration'), 'Box')
    features = _str(specs.get('Features'), 'Factory Sealed')

    # Build header lines
    header_title = title.upper()
    highlight1 = f"{manufacturer} &bull; {year}" if manufacturer and year else manufacturer or year or "Collectible Trading Cards"
    highlight2 = f"Factory Sealed &mdash; {franchise}" if franchise else "Factory Sealed"
    media = movie or tv_show or franchise
    italic_line = f"A great addition to any {media} collection." if media else "A great addition to any collector's shelf."

    # Build description body
    desc_intro = f"Offering one factory sealed {config.lower()} of"
    if year and manufacturer:
        desc_intro += f" {year} {manufacturer}"
    elif manufacturer:
        desc_intro += f" {manufacturer}"
    desc_intro += f" <b>{set_name or franchise}</b> trading cards."
    if franchise and set_name and franchise.lower() not in set_name.lower():
        desc_intro += f" Part of the {franchise} franchise."

    desc_extra = "This item has been stored in a smoke-free, climate-controlled environment since purchase."

    # Build "What you get" bullets
    bullets = [f"One (1) factory sealed {config.lower()} of {set_name or franchise} Trading Cards"]
    if 'Factory Sealed' in features:
        bullets.append("Factory sealed with original shrink wrap")
    if config.lower() == 'box':
        bullets.append("Possible chase and insert cards in sealed packs (not guaranteed per box)")

    bullets_html = '\n'.join(f'<li>{b}</li>' for b in bullets)

    return f'''<table align="center" style="border-spacing:0px; width:100%; max-width:100%;"><tbody><tr><td><table background="https://media.samscollectibles.net/assets/demim_sc.jpg" bgcolor="#1c1c1c" border="2" cellpadding="16" cellspacing="8" style="width:100%; max-width:100%;"><tbody><tr><td><font rwr="1" size="4">

<center>
<font face="verdana, arial, helvetica" size="5" color="#87ceeb"><b>{header_title}</b></font>
<br><br>
<font face="verdana, arial, helvetica" size="3" color="#ff9363">{highlight1}</font>
<br>
<font face="verdana, arial, helvetica" size="3" color="#66e0d0">{highlight2}</font>
<br>
<font face="verdana, arial, helvetica" size="2" color="linen"><i>{italic_line}</i></font>
</center>

<hr>

<center><font face="verdana, arial, helvetica" size="4" color="yellow"><b>DESCRIPTION</b></font></center>
<br>
<font face="verdana, arial, helvetica" size="3" color="linen">
{desc_intro}
<br><br>
{desc_extra}
<br><br>
<b>What you get:</b>
<ul>
{bullets_html}
</ul>
</font>

<hr>

<center><font face="verdana, arial, helvetica" size="4" color="yellow"><b>CONDITION</b></font></center>
<br>
<font face="verdana, arial, helvetica" size="3" color="linen">
This item is <b>factory sealed</b> with original shrink wrap intact. Shows minor shelf wear consistent with age but is in excellent overall condition. Please review all photos carefully as they are part of the description.
</font>

<hr>

<center><font face="verdana, arial, helvetica" size="4" color="yellow"><b>SHIPPING</b></font></center>
<br>
<font face="verdana, arial, helvetica" size="3" color="linen">
Shipped with care using USPS Ground Advantage with tracking. Item will be packaged securely to prevent damage during transit and to ensure safe arrival. <b>We offer combine shipping.</b> Please message us before checkout if you are purchasing multiple items so we can provide a combined shipping invoice.
</font>

<hr>

<center><font face="verdana, arial, helvetica" size="4" color="yellow"><b>FEEDBACK</b></font></center>
<br>
<font face="verdana, arial, helvetica" size="3" color="linen">
Your satisfaction is our priority. If you have any questions or concerns about your order, please message us before leaving feedback and we will make it right. Thank you for shopping with Sam's Collectibles!
</font>

</font></td></tr></tbody></table></td></tr></tbody></table>'''
