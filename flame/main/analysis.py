import argparse
import os
from io import BytesIO
import mitk
from pathlib import Path
import pydicom
import shutil
import shlex
import sys
import tarfile

from bpreg.inference.inference_model import InferenceModel
from flame.star import StarAnalyzer, StarAggregator, StarModel


class InputCrawler:
    def __init__(self, file_endings=None):
        self.file_endings = tuple(file_endings or [".dcm", ".nii", ".nii.gz", ".nrrd"])

    def sanitize_case_name(self, value):
        value = str(value).strip().replace(" ", "_")
        cleaned = "".join(c if c.isalnum() or c in "._-" else "_" for c in value)
        return cleaned.strip("._-") or "case"

    def unique_case_name(self, name, used):
        if name not in used:
            used.add(name)
            return name
        i = 2
        while f"{name}_{i}" in used:
            i += 1
        used.add(f"{name}_{i}")
        return f"{name}_{i}"

    def crawl_inputs(self, target_dir):
        inputs = []
        used_names = set()
        series_map = {}

        allow_dicom = ".dcm" in self.file_endings
        volume_suffixes = tuple(e for e in self.file_endings if e != ".dcm")

        for root, _, files in os.walk(target_dir):
            for fname in files:
                path = os.path.join(root, fname)
                lower = fname.lower()

                if volume_suffixes and lower.endswith(volume_suffixes):
                    if lower.endswith(".nii.gz"):
                        raw_name = fname[:-len(".nii.gz")]
                    else:
                        raw_name = Path(fname).stem

                    case_name = self.unique_case_name(
                        self.sanitize_case_name(raw_name),
                        used_names,
                    )

                    inputs.append({
                        "type": "volume",
                        "path": path,
                        "case_name": case_name,
                    })
                    continue

                if allow_dicom and lower.endswith(".dcm"):
                    try:
                        ds = pydicom.dcmread(
                            path,
                            stop_before_pixels=True,
                            force=True,
                            specific_tags=[
                                "StudyInstanceUID",
                                "SeriesInstanceUID",
                                "PatientID",
                                "Modality",
                                "SeriesDescription",
                            ],
                        )
                    except Exception:
                        continue

                    study_uid = str(getattr(ds, "StudyInstanceUID", "")).strip()
                    series_uid = str(getattr(ds, "SeriesInstanceUID", "")).strip()
                    if not series_uid:
                        continue

                    rel_parts = Path(os.path.relpath(path, target_dir)).parts
                    top_folder = rel_parts[0] if len(rel_parts) > 1 else ""

                    key = (study_uid, series_uid)
                    entry = series_map.setdefault(key, {
                        "type": "dicom",
                        "study_uid": study_uid,
                        "series_uid": series_uid,
                        "patient_id": str(getattr(ds, "PatientID", "")).strip(),
                        "modality": str(getattr(ds, "Modality", "")).strip(),
                        "series_description": str(getattr(ds, "SeriesDescription", "")).strip(),
                        "case_name": top_folder or str(getattr(ds, "PatientID", "")).strip() or series_uid[-24:],
                        "files": [],
                    })
                    entry["files"].append(path)

        for entry in series_map.values():
            entry["case_name"] = self.unique_case_name(
                self.sanitize_case_name(entry["case_name"]),
                used_names,
            )
            inputs.append(entry)

        return sorted(inputs, key=lambda x: x["case_name"])

    def prepare_inference_input(self, entry, converted_root):
        if entry["type"] == "volume":
            return entry["path"]

        os.makedirs(converted_root, exist_ok=True)

        case_name = entry["case_name"]
        output_path = os.path.join(converted_root, f"{case_name}.nii.gz")
        if os.path.exists(output_path):
            return output_path

        dicom_path = os.path.join(converted_root, f".{case_name}_dicom")
        if os.path.exists(dicom_path):
            shutil.rmtree(dicom_path)
        os.makedirs(dicom_path)

        for i, src in enumerate(sorted(entry["files"])):
            dst = os.path.join(dicom_path, f"{i:05d}_{Path(src).name}")
            try:
                os.symlink(src, dst)
            except OSError:
                shutil.copy2(src, dst)

        images = mitk.IOUtil.load(dicom_path)
        if len(images) != 1:
            raise ValueError(f"Expected one image from {dicom_path}, got {len(images)}")

        mitk.IOUtil.save(images[0], output_path)

        if not os.path.exists(output_path):
            raise ValueError(f"MITK did not create output file: {output_path}")

        return output_path


def stage_input_data(data_dict, archive_name, target_dir):
    os.makedirs(target_dir, exist_ok=True)

    items = (
        [(archive_name, data_dict[archive_name])]
        if archive_name in data_dict
        else list(data_dict.items())
    )

    for name, content in items:
        buffer = BytesIO(content)

        if tarfile.is_tarfile(buffer):
            buffer.seek(0)
            with tarfile.open(fileobj=buffer) as tar:
                safe_extract_tar(tar, target_dir)
        else:
            out = os.path.join(target_dir, name)
            os.makedirs(os.path.dirname(out), exist_ok=True)
            with open(out, "wb") as f:
                f.write(content)


def safe_extract_tar(tar, target_dir):
    target_dir = os.path.abspath(target_dir)

    for member in tar.getmembers():
        path = os.path.abspath(os.path.join(target_dir, member.name))

        if not path.startswith(target_dir + os.sep) and path != target_dir:
            raise ValueError(f"Unsafe tar path: {member.name}")

        if not (member.isfile() or member.isdir()):
            raise ValueError(f"Unsupported tar member: {member.name}")

    tar.extractall(target_dir)


class MyAnalyzer(StarAnalyzer):
    def __init__(self, flame, image_data, file_endings=[".dcm", ".nii", ".nii.gz", ".nrrd"]):
        """
        Initializes the Analyzer node.
        :param flame: Instance of FlameCoreSDK to interact with the FLAME components.
        """

        super().__init__(flame)
        self.image_data = image_data
        self.images = '/tmp/images'
        self.converted = '/tmp/converted'
        self.crawler = InputCrawler(file_endings)

        print("Init of analyzer finished ...")

    def analysis_method(self, data, aggregator_results):
        """
        Performs analysis on the retrieved data from data sources, including z-spacing validity checks and examined body part extraction.
        Only for CT images.

        :param data: List of dictionaries, each representing data from one data source.
                    - Each dictionary contains keys as query names and values as the data results.
                    - For example, values may be dicts (FHIR) or strings (S3 archive content).
        :param aggregator_results: Aggregated results from previous iterations.
                                - None for the first iteration.
                                - Contains output from the aggregator’s aggregation_method in later iterations.
        :return: Dictionary containing the results of the analysis for each image node,
                e.g., patient counts, error messages, or check results.
        """

        stage_input_data(data[0], self.image_data, self.images)
        print("Images have been loaded")

        # Crawl the extracted archive and prepare every supported input.
        inputs = self.crawler.crawl_inputs(self.images)

        print(f'Found {len(inputs)} inputs.')

        # initialize model
        model_base_dir = "src/models/public_bpr_model/"
        model_inference = InferenceModel(model_base_dir, warning_to_error=True, gpu=False)

        result_dict = {}
        # Loop for every input-file
        for input_entry in inputs:

            result = {}

            print(f"Processing {input_entry['case_name']}")

            img_id = input_entry["case_name"]

            try:
                inference_input = self.crawler.prepare_inference_input(
                    input_entry, self.converted
                )
                result['json'] = model_inference.nifti2json(nifti_path=inference_input)
            except ValueError as e:
                result["basic_error"] = str(e)
                print(f"notification: skipping case {img_id}: {e}")
            except Exception as e:
                result["basic_error"] = str(e)
                print(f"notification: skipping case {img_id}: {e}")

            result_dict[img_id] = result

        print("Processing done.")

        return result_dict


class MyAggregator(StarAggregator):
    def __init__(self, flame):
        """
        Initializes the custom Aggregator node.

        :param flame: Instance of FlameCoreSDK to interact with the FLAME components.
        """
        super().__init__(flame)

        print("Init of aggregator finished ...")


    def aggregation_method(self, analysis_results):
        """
        Aggregates the analysis results from multiple analyzers into one dictionary.

        :return: analysis_results (dict): A single dictionary combining all individual results.
        """
        return analysis_results
    

    def has_converged(self, result, last_result, num_iterations=None):
        """
        Checks whether the analysis has converged if 'simple_analysis' in 'StarModel' is set to False.
        Always returns True, since only one iteration round is performed.  

        :return (bool): True, indicating convergence after a single round.
        """
        return True 


def main():
    """
    Entry point to initialize and run the StarModel pipeline.
    Parses console arguments and passes them to MyAnalyzer.
    """
    parser = argparse.ArgumentParser(description="Run StarModel pipeline with custom analyzer parameters.")
    parser.add_argument("--image_data", type=str, default="images.tar", help="Name of the input images tar file")
    parser.add_argument("--file_endings", nargs="+", default=[".dcm", ".nii", ".nii.gz", ".nrrd"], help="List of file endings to include")
    parser.add_argument("--query_keys", nargs="*", default=None, help="Optional S3 keys for StarModel query")

    argv = sys.argv[1:]
    if len(argv) == 1 and " " in argv[0]:
        argv = shlex.split(argv[0])

    args, unknown = parser.parse_known_args(argv)
    analyzer_kwargs = {'image_data':args.image_data,
                       'file_endings': args.file_endings}
    
    query = args.query_keys if args.query_keys is not None else [args.image_data]

    StarModel(
        analyzer=MyAnalyzer,
        aggregator=MyAggregator,
        data_type='s3',
        query=query,
        simple_analysis=True,
        output_type='pickle',
        analyzer_kwargs=analyzer_kwargs
    )


if __name__ == "__main__":
    main()




