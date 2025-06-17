"""

"""
import logging
from backend.db.models import Run, Sample, Procedure, ProcedureSampleAssociation
from backend.excel.parsers import DefaultKEYVALUEParser, DefaultTABLEParser

logger = logging.getLogger(f"submissions.{__name__}")

# class PCRResultsParser(DefaultParser):
#     pass

class PCRInfoParser(DefaultKEYVALUEParser):
    default_range_dict = [dict(
        start_row=1,
        end_row=24,
        key_column=1,
        value_column=2,
        sheet="Results"
    )]

    # def __init__(self, filepath: Path | str, range_dict: dict | None = None):
    #     super().__init__(filepath=filepath, range_dict=range_dict)
    #     self.worksheet = self.workbook[self.range_dict['sheet']]
    #     self.rows = range(self.range_dict['start_row'], self.range_dict['end_row'] + 1)
    #
    # @property
    # def parsed_info(self) -> Generator[Tuple, None, None]:
    #     for row in self.rows:
    #         key = self.worksheet.cell(row, self.range_dict['key_column']).value
    #         if key:
    #             key = re.sub(r"\(.*\)", "", key)
    #             key = key.lower().replace(":", "").strip().replace(" ", "_")
    #             value = self.worksheet.cell(row, self.range_dict['value_column']).value
    #             value = dict(value=value, missing=False if value else True)
    #             yield key, value
    #

    def to_pydantic(self):
        # from backend.db.models import Procedure
        data = {key: value for key, value in self.parsed_info}
        data['filepath'] = self.filepath
        return self._pyd_object(**data, parent=self.procedure)

    # @property
    # def pcr_info(self) -> dict:
    #     """
    #     Parse general info rows for all types of PCR results
    #     """
    #     info_map = self.submission_obj.get_submission_type().sample_map['pcr_general_info']
    #     sheet = self.xl[info_map['sheet']]
    #     iter_rows = sheet.iter_rows(min_row=info_map['start_row'], max_row=info_map['end_row'])
    #     pcr = {}
    #     for row in iter_rows:
    #         try:
    #             key = row[0].value.lower().replace(' ', '_')
    #         except AttributeError as e:
    #             logger.error(f"No key: {row[0].value} due to {e}")
    #             continue
    #         value = row[1].value or ""
    #         pcr[key] = value
    #     pcr['imported_by'] = getuser()
    #     return pcr


class PCRSampleParser(DefaultTABLEParser):
    """Object to pull data from Design and Analysis PCR export file."""

    default_range_dict = [dict(
        header_row=25,
        sheet="Results"
    )]

    @property
    def parsed_info(self):
        output = [item for item in super().parsed_info]
        merge_column = "sample"
        sample_names = list(set([item['sample'] for item in output]))
        for sample in sample_names:
            multi = dict()
            sois = [item for item in output if item['sample'] == sample]
            for soi in sois:
                multi[soi['target']] = {k: v for k, v in soi.items() if k != "target" and k != "sample"}
            yield {sample: multi}

    def to_pydantic(self):
        logger.debug(f"running to pydantic")
        for item in self.parsed_info:
            sample_obj = Sample.query(sample_id=list(item.keys())[0])
            logger.debug(f"Sample object {sample_obj}")
            assoc = ProcedureSampleAssociation.query(sample=sample_obj, procedure=self.procedure)
            if assoc and not isinstance(assoc, list):
                yield self._pyd_object(results=list(item.values())[0], parent=assoc)
            else:
                continue

