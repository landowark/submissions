from __future__ import annotations

from backend.validators.pydant.abstract import PydProcedureType, PydSubmissionType, PydTips


def test_pydtips_uses_manufacturer_ref_capacity_for_generated_name():
    tips = PydTips(manufacturer="TipCo", ref="T-9", capacity=200)

    assert tips.name == "TipCo - T-9(200uL)"


def test_pydtips_keeps_explicit_name_when_present():
    tips = PydTips(name="Custom Tips", manufacturer="TipCo", ref="T-9", capacity=200)

    assert tips.name == "Custom Tips"


def test_default_submission_template_is_used_when_missing():
    submission_type = PydSubmissionType()

    assert submission_type.file_name_template == (
        "{{rsl_plate_number}}{% if _clientsubmission %}_{{_clientsubmission.submitter_plate_id}}{% endif %}_{{_completed_date}}"
    )


def test_proceduretype_defaults_to_default_submissiontype():
    procedure_type = PydProcedureType(name="Test Procedure")

    assert procedure_type.submissiontype == ["Default SubmissionType"]
