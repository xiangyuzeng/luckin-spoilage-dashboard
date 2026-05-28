"""SKU catalog — single source of truth for the 44 物料 specs the dashboard tracks.

Cost, conversion ratios, and unit codes are fetched from SCM at pull time and
stored in cache/spec_metadata.json. This file only carries the user-supplied
human label and category grouping (which SCM does not record).

To add or remove a SKU: edit SKU_CATALOG and re-run pipeline/pull.py.
"""

# Unit code → display label (from luckyus_scm_commodity.t_mdm_unit).
UNIT_LABELS = {
    "QU013": "mL",
    "QU005": "g",
    "QU009": "个",
    "QU002": "瓶",
    "QU011": "箱",
    "QU006": "盒",
    "QU041": "罐",
    "QU051": "支",
}

CATEGORIES = [
    ("dairy",     "奶 / Dairy"),
    ("coffee",    "咖啡豆 / Coffee"),
    ("bakery",    "烘焙 / Bakery"),
    ("syrup",     "糖浆 / Syrups"),
    ("sauce",     "酱料 / Sauces"),
    ("powder",    "粉 / Powders"),
    ("seasoning", "调味 / Seasoning"),
    ("beverage",  "饮料 / Beverages"),
    ("other",     "其他 / Other"),
]
CATEGORY_LABEL = dict(CATEGORIES)

# Display name (label_cn) follows the user's submitted naming.
SKU_CATALOG = {
    # Dairy (9)
    "GS07785-01": {"cat": "dairy",    "label_cn": "Cream-O-Land 2% 减脂奶 4/1 GAL CS"},
    "GS07786-01": {"cat": "dairy",    "label_cn": "Cream-O-Land 全脂奶 4/1 GAL CS"},
    "GS07788-01": {"cat": "dairy",    "label_cn": "Cream-O-Land 脱脂奶 4/1 GAL CS"},
    "GS07786-02": {"cat": "dairy",    "label_cn": "Cream-O-Land 全脂奶 1GAL*4 DSD"},
    "GS07506-01": {"cat": "dairy",    "label_cn": "菲诺厚椰乳 1kg*12/箱"},
    "GS07565-01": {"cat": "dairy",    "label_cn": "Oatly 燕麦奶 12/32 OZ CS"},
    "GS07579-01": {"cat": "dairy",    "label_cn": "Califia 巴旦木奶 12/32 OZ CS"},
    "GS07575-01": {"cat": "dairy",    "label_cn": "Wholesome 冰淇淋奶浆 6/64 OZ CS"},
    "GS07743-01": {"cat": "dairy",    "label_cn": "Wholesome 奶油 12/32 OZ CS"},
    # Coffee (5)
    "GS07465-01": {"cat": "coffee",   "label_cn": "Luckin Medium Roast Espresso 6/2lb"},
    "GS07466-01": {"cat": "coffee",   "label_cn": "Luckin Dark Roast Espresso 6/2lb"},
    "GS07469-01": {"cat": "coffee",   "label_cn": "Luckin Cold Brew Blend 5/5lb"},
    "GS07468-01": {"cat": "coffee",   "label_cn": "Luckin Decaf Blend 6/2lb"},
    "GS07470-01": {"cat": "coffee",   "label_cn": "Luckin Drip Coffee Blend 6/2lb"},
    # Bakery (5)
    "GS08253-01": {"cat": "bakery",   "label_cn": "J.K Pâtisserie 巧克力曲奇"},
    "GS08251-01": {"cat": "bakery",   "label_cn": "J.K Pâtisserie 双重巧克力玛芬"},
    "GS08252-01": {"cat": "bakery",   "label_cn": "J.K Pâtisserie 巴旦木可颂"},
    "GS08254-01": {"cat": "bakery",   "label_cn": "J.K Pâtisserie 巧克力可颂"},
    "GS07859-01": {"cat": "bakery",   "label_cn": "蛋堡可颂 12/4.9 OZ CS"},
    # Syrups (12)
    "GS07490-01": {"cat": "syrup",    "label_cn": "DVG 肉桂糖浆 4/750ML CS"},
    "GS07491-01": {"cat": "syrup",    "label_cn": "DVG PL 榛子糖浆 4/750ML CS"},
    "GS07494-01": {"cat": "syrup",    "label_cn": "DVG PL 蔗糖糖浆 4/750ML CS"},
    "GS07495-01": {"cat": "syrup",    "label_cn": "DVG PL 香草糖浆 4/750ML CS"},
    "GS07496-01": {"cat": "syrup",    "label_cn": "DVG PL 焦糖糖浆 4/750ML CS"},
    "GS07749-01": {"cat": "syrup",    "label_cn": "DVG PL 草莓糖浆 4/750ML CS"},
    "GS07492-01": {"cat": "syrup",    "label_cn": "香草冰沙粉 5/3.5lb CS"},
    "GS08300-01": {"cat": "syrup",    "label_cn": "爆米花糖浆 1L/瓶"},
    "GS08916-01": {"cat": "syrup",    "label_cn": "焦糖布丁糖浆 12/1L CS"},
    "GS08917-01": {"cat": "syrup",    "label_cn": "太妃糖浆 12/1L CS"},
    "GS09538-01": {"cat": "syrup",    "label_cn": "Monin 柚子果泥 1L*4/CTN"},
    "GS09631-01": {"cat": "syrup",    "label_cn": "DVG 夏威夷海盐焦糖糖浆 750ml*4"},
    # Sauces (3)
    "GS07746-01": {"cat": "sauce",    "label_cn": "DVG 巧克力酱 6/0.5GAL CS"},
    "GS07769-01": {"cat": "sauce",    "label_cn": "Lyons Magnus 焦糖淋酱 12/17 OZ CS"},
    "GS07763-01": {"cat": "sauce",    "label_cn": "甜炼乳 24/14 OZ CS"},
    # Powders (6)
    "GS07738-01": {"cat": "powder",   "label_cn": "McCormick 肉桂粉 6/18 OZ CS"},
    "GS07738-02": {"cat": "powder",   "label_cn": "McCormick 肉桂粉 6/29 OZ CS"},
    "GS07744-02": {"cat": "powder",   "label_cn": "顺大可可粉 200g*30/CTN"},
    "GS07964-01": {"cat": "powder",   "label_cn": "茉莉花茶粉 300g/袋"},
    "GS07976-01": {"cat": "powder",   "label_cn": "京都抹茶粉 20/100g CS"},
    "GS09432-01": {"cat": "powder",   "label_cn": "顺大云感粉 300g*20/CTN"},
    # Seasoning (1)
    "GS09530-01": {"cat": "seasoning","label_cn": "莫顿精细海盐 17.60oz*12/CTN"},
    # Beverages (2)
    "GS07510-01": {"cat": "beverage", "label_cn": "菲诺椰皇水 12/1kg CS"},
    "GS09641-01": {"cat": "beverage", "label_cn": "Polar 原味苏打水 20oz*24/CTN"},
    # Other (1)
    "GS07586-01": {"cat": "other",    "label_cn": "ISI 奶油枪气弹 8.4g*10*36/箱"},
}

# Sanity: 44 SKUs across 9 categories.
assert len(SKU_CATALOG) == 44, len(SKU_CATALOG)
assert all(v["cat"] in CATEGORY_LABEL for v in SKU_CATALOG.values())
