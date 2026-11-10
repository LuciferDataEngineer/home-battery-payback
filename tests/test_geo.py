from hbp.geo import normalise_postcode, state_of_postcode


def test_postcode_ranges():
    assert state_of_postcode("2000") == "NSW"
    assert state_of_postcode("2600") == "ACT"
    assert state_of_postcode("3000") == "VIC"
    assert state_of_postcode("4000") == "QLD"
    assert state_of_postcode("5000") == "SA"
    assert state_of_postcode("6000") == "WA"
    assert state_of_postcode("7000") == "TAS"
    assert state_of_postcode("0800") == "NT"


def test_poa_prefix():
    assert normalise_postcode("POA2000") == "2000"
    assert normalise_postcode("800") == "0800"
    assert normalise_postcode("not-a-postcode") is None
