import argparse
import os
from io import BytesIO
import shlex
import sys
import tarfile

from bpreg.inference.inference_model import InferenceModel
from flame.star import StarAnalyzer, StarAggregator, StarModel


class MyAnalyzer(StarAnalyzer):
    def __init__(self, flame, image_data, file_endings = [".nii", ".nii.gz", ".nrrd"]):
        """
        Initializes the Analyzer node.
        :param flame: Instance of FlameCoreSDK to interact with the FLAME components.
        """

        super().__init__(flame)

        self.file_endings = file_endings

        self.image_data = image_data

        self.output = '/tmp/output'
        self.images = '/tmp/images'

        self.image_paths = []

        print("Init of analyzer finished ...")



    def get_files(self, data_dict, archive_name, target_dir):
        """
        Extracts image data from a tar archive stored in-memory and collects paths to image files.

        :param data_dict: Dictionary containing the archive data keyed by archive names.
                        - Each value is raw byte content of a tar archive.
        :param archive_name: The key to select the specific archive from data_dict to extract.
        :param target_dir: Directory where the archive will be extracted.
                        - Created if it does not exist.
        :return: List of paths pointing to extracted image files.
        """
        
        os.makedirs(target_dir, exist_ok=True)

        print(f"Extracting {archive_name} to {target_dir}...")

        # Load, open and extract tar file
        tar_obj = BytesIO(data_dict[archive_name])
        with tarfile.open(fileobj=tar_obj) as tar:
            tar.extractall(path=target_dir)

        print("Images have been loaded")

        all_paths = []
        for root, dirs, files in os.walk(target_dir):

            # Check files
            for fname in files:
                ext = os.path.splitext(fname)[1].lower()
                if ext in self.file_endings:
                    all_paths.append(os.path.join(root, fname))

        return all_paths



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

        
        self.image_paths = self.get_files(data[0], self.image_data, self.images)

        print(f'Found {len(self.image_paths)} files.')

        # initialize model
        model_base_dir = "src/models/public_bpr_model/"
        model_inference = InferenceModel(
            model_base_dir,  warning_to_error=True, gpu=False,
        )

        result_dict = {}
        # Loop for every input-file
        for input_file in self.image_paths:

            result = {}

            print(f'Processing {input_file}')

            img_id = os.path.basename(input_file)

            try:
                result['json'] = model_inference.nifti2json(nifti_path=input_file)
            except Exception as e:
                result["basic_error"] = str(e)

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
    parser.add_argument("--file_endings", nargs="+", default=[".nii", ".nii.gz", ".nrrd"], help="List of file endings to process")
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




