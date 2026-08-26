# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""LEG-MOD-04: model licence notices derived from licence text (no model list)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    from halbert_core.model.attribution import (
        as_dict,
        classify_license_text,
        license_for_ollama_model,
        notices_for,
        provider_terms,
    )
except ImportError:
    from halbert_core.halbert_core.model.attribution import (  # noqa: E402
        as_dict,
        classify_license_text,
        license_for_ollama_model,
        notices_for,
        provider_terms,
    )

APACHE = """
                                 Apache License
                           Version 2.0, January 2004
                        http://www.apache.org/licenses/

   TERMS AND CONDITIONS FOR USE, REPRODUCTION, AND DISTRIBUTION
   4. Redistribution. You may reproduce and distribute copies of the Work ...
"""

MIT = """MIT License

Copyright (c) 2025 Example Labs

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal ...
"""

# A community licence with a mandatory display phrase and a NOTICE-file sentence
# (wording pattern used by Meta's community licences; the phrase is whatever the
# licence says — the classifier does not know any model names).
COMMUNITY = """
EXAMPLE 9.1 COMMUNITY LICENSE AGREEMENT
Example 9.1 Version Release Date: January 1, 2030

1. License Rights and Redistribution.
b. Redistribution and Use.
i. If you distribute or make available the Example Materials (or any derivative works thereof), or a product or service
that contains any of them, you shall (A) provide a copy of this Agreement with any such Example Materials; and (B)
prominently display “Built with Example” on a related website, user interface, blogpost, about page, or product
documentation. If you use the Example Materials or any outputs or results of the Example Materials to create, train,
fine tune, or otherwise improve an AI model, which is distributed or made available, you shall also include “Example”
at the beginning of any such AI model name.
iii. You must retain in all copies of the Example Materials that you distribute the following attribution notice within
a “Notice” text file distributed as a part of such copies: “Example 9.1 is licensed under the Example 9.1 Community
License, Copyright © Example Platforms, Inc. All Rights Reserved.”
5. Use of the Example Materials must comply with the Example Acceptable Use Policy.
"""

# A licence whose "Built with" phrase only applies to models derived from it.
DERIVED_ONLY = """
EXAMPLE LICENSE AGREEMENT
Release Date: September 19, 2029
3. Redistribution.
d. If you use the Materials or any outputs or results of the Materials to create, train, fine-tune, or improve an AI
model that is distributed or made available, you shall prominently display “Built with Example” or “Improved using
Example” in the related product documentation.
"""

RESEARCH = """
EXAMPLE RESEARCH LICENSE AGREEMENT
1. Grant of Rights. Licensor grants you a non-exclusive license to use the Materials FOR NON-COMMERCIAL PURPOSES ONLY.
"""

MODEL_AGREEMENT = """
EXAMPLECORP LICENSE AGREEMENT
Version 1.0, 23 October 2029
Section 5. Use-based restrictions. You must require all your users to comply with the restrictions in Attachment A.
"""


def test_apache_has_no_display_notice():
    info = classify_license_text(APACHE)
    assert info.name == "Apache License 2.0"
    assert info.license_id == "Apache-2.0"
    assert info.notice is None and info.notice_file_sentence is None
    assert not info.non_commercial


def test_mit_detected_from_permission_grant():
    info = classify_license_text(MIT)
    assert info.license_id == "MIT"
    assert info.notice is None


def test_community_licence_yields_exact_display_phrase_and_notice_sentence():
    info = classify_license_text(COMMUNITY)
    assert info.name == "Example 9.1 Community License Agreement"
    assert info.license_id == "LicenseRef-Example-9.1-Community-License"
    assert info.notice == "Built with Example"          # exact phrase, taken from the licence
    assert info.notice_file_sentence == (
        "Example 9.1 is licensed under the Example 9.1 Community License, "
        "Copyright © Example Platforms, Inc. All Rights Reserved."
    )
    assert info.acceptable_use_policy is True
    assert info.derived_model_notice is None


def test_display_phrase_inside_training_clause_is_not_a_product_notice():
    info = classify_license_text(DERIVED_ONLY)
    assert info.name == "Example License Agreement"
    assert info.notice is None
    assert info.derived_model_notice == "Built with Example"


def test_research_licence_is_non_commercial():
    info = classify_license_text(RESEARCH)
    assert "Research License" in info.name
    assert info.non_commercial is True
    assert info.notice is None


def test_generic_license_agreement_title_is_reported_without_invented_notice():
    info = classify_license_text(MODEL_AGREEMENT)
    assert info.name == "Examplecorp License Agreement"
    assert info.notice is None
    assert info.license_id.startswith("LicenseRef-")


def test_unknown_text_falls_back_to_title_line():
    info = classify_license_text("Some Bespoke Terms v3\n\nYou may use this model.")
    assert info.name == "Some Bespoke Terms v3"
    assert info.license_id == "LicenseRef-Unknown"
    assert info.notice is None


def test_empty_input_is_none():
    assert classify_license_text(None) is None
    assert classify_license_text("   \n") is None
    assert as_dict(None) is None


def test_license_for_ollama_model_uses_fetcher():
    calls = []

    def fake_fetch(base_url, model):
        calls.append((base_url, model))
        return COMMUNITY

    info = license_for_ollama_model("http://localhost:11434", "some-model:latest", fetcher=fake_fetch)
    assert calls == [("http://localhost:11434", "some-model:latest")]
    assert info.notice == "Built with Example"

    assert license_for_ollama_model("http://x", "m", fetcher=lambda *_: None) is None


def test_notices_are_deduplicated():
    a = classify_license_text(COMMUNITY)
    b = classify_license_text(COMMUNITY)
    c = classify_license_text(APACHE)
    assert notices_for([a, c, b, None]) == ["Built with Example"]


def test_provider_terms_never_name_a_model():
    for p in ("openai", "anthropic", "google", "openai-compatible", "lm-studio"):
        t = provider_terms(p)
        assert t is not None and t.source == "provider" and t.notice is None
    assert provider_terms("ollama") is None  # per-model licence comes from /api/show instead


def test_as_dict_is_json_friendly():
    d = as_dict(classify_license_text(COMMUNITY))
    assert d["notice"] == "Built with Example"
    assert d["source"] == "license-text"
    assert isinstance(d["acceptable_use_policy"], bool)
