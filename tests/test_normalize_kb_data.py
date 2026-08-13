from app.main import normalize_kb_data


def test_missing_section_uses_template_defaults():
    normalized = normalize_kb_data({})
    assert normalized["performance_metrics"]["current"] == {}
    assert normalized["confusion_matrix"]["derived"] == {}
    assert normalized["bias_report"]["metrics"] == []


def test_section_present_but_wrong_top_level_type_preserves_container_shape():
    normalized = normalize_kb_data({
        "performance_metrics": "unable to parse data from source",
        "bias_report": "unable to parse data from source",
    })
    assert normalized["performance_metrics"]["current"] == {}
    assert normalized["performance_metrics"]["reference"] == {}
    assert normalized["bias_report"]["metrics"] == []


def test_section_present_with_malformed_sub_field_falls_back_to_empty_container():
    normalized = normalize_kb_data({
        "performance_metrics": {"current": "N/A", "reference": {"accuracy": 0.9}},
        "confusion_matrix": {"derived": None},
        "bias_report": {"metrics": "n/a"},
    })
    assert normalized["performance_metrics"]["current"] == {}
    assert normalized["performance_metrics"]["reference"] == {"accuracy": 0.9}
    assert normalized["confusion_matrix"]["derived"] == {}
    assert normalized["bias_report"]["metrics"] == []
