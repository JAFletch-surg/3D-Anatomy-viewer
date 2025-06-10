# app/model_processor.py
import os
import logging
from .test_mesh import extract_transformed_mesh

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def process_segmentation(filepath):
   
    try:
        logger.info(f"Starting segmentation processing for file: {filepath}")
        
        # validate input
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Input file not found: {filepath}")
        
        # Check file extension
        if not filepath.endswith(('.nii', '.nii.gz')):
            raise ValueError("Input file must be a NIfTI file (.nii or .nii.gz)")
        
        # Process the segmentation
        output_path = extract_transformed_mesh(filepath)
        
        # Verify output file was created
        if not os.path.exists(output_path):
            raise FileNotFoundError(f"Processing completed but output file not found: {output_path}")
        
        logger.info(f"Successfully processed segmentation. Output file: {output_path}")
        return output_path
        
    except Exception as e:
        logger.error(f"Error processing segmentation: {str(e)}")
        raise Exception(f"Failed to process segmentation: {str(e)}")
    finally:
        # Cleanup temporary files if needed
        try:
            tmp_dir = os.path.join(os.path.dirname(filepath), 'tmp')
            if os.path.exists(tmp_dir):
                for f in os.listdir(tmp_dir):
                    os.remove(os.path.join(tmp_dir, f))
                os.rmdir(tmp_dir)
        except Exception as e:
            logger.warning(f"Failed to cleanup temporary files: {str(e)}")

