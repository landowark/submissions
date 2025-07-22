"""

"""
import logging
from backend.db.models import Run, Sample, Procedure, ProcedureSampleAssociation
from backend.excel.parsers import DefaultKEYVALUEParser, DefaultTABLEParser
from pathlib import Path

logger = logging.getLogger(f"submissions.{__name__}")


# class PCRResultsParser(DefaultParser):
#     pass

class PCRInfoParser(DefaultKEYVALUEParser):
    pyd_name = "PydResults"

    default_range_dict = [dict(
        start_row=1,
        end_row=24,
        key_column=1,
        value_column=2,
        sheet="Results"
    )]

    def __init__(self, filepath: Path | str, range_dict: dict | None = None, procedure=None):
        super().__init__(filepath=filepath, range_dict=range_dict)
        self.procedure = procedure

    def to_pydantic(self):
        # from backend.db.models import Procedure
        data = dict(results={key: value for key, value in self.parsed_info}, filepath=self.filepath,
                    result_type="PCR")
        return self._pyd_object(**data, parent=self.procedure)


class PCRSampleParser(DefaultTABLEParser):
    """Object to pull data from Design and Analysis PCR export file."""

    pyd_name = "PydResults"

    default_range_dict = [dict(
        header_row=25,
        sheet="Results"
    )]

    def __init__(self, filepath: Path | str, range_dict: dict | None = None, procedure=None):
        super().__init__(filepath=filepath, range_dict=range_dict)
        self.procedure = procedure

    @property
    def parsed_info(self):
        output = [item for item in super().parsed_info]
        merge_column = "sample"
        sample_names = list(set([item['sample'] for item in output]))
        for sample in sample_names:
            multi = dict(result_type="PCR")
            sois = [item for item in output if item['sample'] == sample]
            for soi in sois:
                multi[soi['target']] = {k: v for k, v in soi.items() if k != "target" and k != "sample"}
            yield {sample: multi}

    def to_pydantic(self):
        logger.debug(f"running to pydantic")
        for item in self.parsed_info:
            # sample_obj = Sample.query(sample_id=list(item.keys())[0])
            # NOTE: Ensure that only samples associated with the procedure are used.
            try:
                sample_obj = next(
                    (sample for sample in self.procedure.sample if sample.sample_id == list(item.keys())[0]))
            except StopIteration:
                continue
            logger.debug(f"Sample object {sample_obj}")
            assoc = ProcedureSampleAssociation.query(sample=sample_obj, procedure=self.procedure)
            if assoc and not isinstance(assoc, list):
                output = self._pyd_object(results=list(item.values())[0], parent=assoc)
                output.result_type = "PCR"
                yield output
            else:
                continue
