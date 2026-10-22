import pytest
from clinic_booking_api.services.normalization import normalize_name, normalize_phone
@pytest.mark.parametrize("raw_phone, expected", [
    ("0712345678", "+254712345678"),
    ("+254712345678", "+254712345678"),
    ("(0712) 345 678", "+254712345678"),
    ("0712-345-678", "+254712345678"),
    ("0112345678", "+254112345678"),
    ("+254 0712 345 678", "+254712345678"),
    ("000254712345678", "+254712345678"),
    ("712345678", "+254712345678")
])
def test_normalize_phone_valid(raw_phone, expected):
    
    assert normalize_phone(raw_phone) == expected

@pytest.mark.parametrize("raw_phone",[
    "+44791123456", 
    ""
]
) 
def test_normalize_phone_invalid(raw_phone):
    with pytest.raises(ValueError):
        normalize_phone(raw_phone)


@pytest.mark.parametrize("name, expected",[
    ("Amina Hassan", "amina hassan"),
    ("   AMinA \tHassan\n", "amina hassan"),
    ("Amina, Hassan.", "amina hassan"),
    ("O'Neil", "o'neil"),
    ("Am i n a", "am i n a"),
    ("Mary-Jane O'neil", "mary-jane o'neil"),
    ("Wanjiru Njeri Kamau", "wanjiru njeri kamau")
])
def test_normalize_name_valid(name, expected):
    assert normalize_name(name) == expected

@pytest.mark.parametrize("name",[
    "",
    "$*&##@",
    "----",
    "....",
    "amina2",
    "amina_hassan",
    "123",
    "R2D2"
])
def test_normalize_name_invalid(name):
    with pytest.raises(ValueError):
        normalize_name(name)