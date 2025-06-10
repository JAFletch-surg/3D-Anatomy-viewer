import os
import numpy as np
import nibabel as nib
from skimage.measure import marching_cubes
import trimesh
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def analyze_nifti(filepath):
    """Analyze the input NIFTI file dimensions and transformations"""
    nii = nib.load(filepath)
    logger.info("\nNIFTI File Analysis:")
    logger.info(f"Image dimensions: {nii.shape}")
    logger.info(f"Voxel dimensions: {nii.header.get_zooms()}")
    logger.info(f"Affine transformation:\n{nii.affine}")
    
    # Calculate real-world bounds
    corners = np.array(list(np.ndindex((2,2,2))))  # Generate corners
    corners = corners * (np.array(nii.shape) - 1)   # Scale to image dimensions
    corners_homo = np.hstack((corners, np.ones((8,1))))  # Make homogeneous
    real_corners = corners_homo @ nii.affine.T    # Transform to real-world
    
    logger.info("\nReal-world bounds:")
    logger.info(f"X: {real_corners[:,0].min():.2f} to {real_corners[:,0].max():.2f}")
    logger.info(f"Y: {real_corners[:,1].min():.2f} to {real_corners[:,1].max():.2f}")
    logger.info(f"Z: {real_corners[:,2].min():.2f} to {real_corners[:,2].max():.2f}")
    
    return nii

def extract_transformed_mesh(filepath):
    
    try:
        # Load and analyze data
        nii = analyze_nifti(filepath)
        data = nii.get_fdata()
        original_affine = nii.affine
        
        # Extract raw meshes using affine transformation
        raw_meshes = []
        for label in range(1, 7):
            if np.any(data == label):
                logger.info(f"\nExtracting label_{label}")
                vertices, faces, _, _ = marching_cubes(data == label)
                
                # Apply affine transformation to vertices (improved method)
                homogeneous_vertices = np.hstack((vertices, np.ones((vertices.shape[0], 1))))
                transformed_vertices = np.dot(homogeneous_vertices, original_affine.T)[:, :3]
                
                raw_meshes.append({
                    'vertices': transformed_vertices,
                    'faces': faces,
                    'label': label
                })
        
        if not raw_meshes:
            raise ValueError("No valid labels found in the segmentation data")
        
        # Calculate scene center in real-world coordinates
        all_vertices = np.vstack([mesh['vertices'] for mesh in raw_meshes])
        scene_center = np.mean(all_vertices, axis=0)
        logger.info(f"\nScene center in real-world coordinates: {scene_center}")
        
        # Create rotation matrix for -90 degrees around X axis (4x4 for proper transformation)
        angle_x = -np.pi/2
        rotation_matrix = np.array([
            [1, 0, 0, 0],
            [0, np.cos(angle_x), -np.sin(angle_x), 0],
            [0, np.sin(angle_x), np.cos(angle_x), 0],
            [0, 0, 0, 1]
        ])
        
        # Process each mesh
        scene = trimesh.Scene()
        processed_meshes = []
        
        for mesh_data in raw_meshes:
            label = mesh_data['label']
            logger.info(f"\nProcessing label_{label}")
            
            # Create mesh
            mesh = trimesh.Trimesh(
                vertices=mesh_data['vertices'],
                faces=mesh_data['faces']
            )
            
            logger.info(f"Initial bounds for label_{label}: {mesh.bounds}")
            
            # Flip normals 
            mesh.invert()
            logger.info(f"Normals flipped to face outward for label_{label}")
            
            # Center and rotate while preserving real-world coordinates
            center_transform = np.eye(4)
            center_transform[:3, 3] = -scene_center
            
            # Combine transformations
            transform = np.dot(rotation_matrix, center_transform)
            
            # Apply transformation
            mesh.apply_transform(transform)
            
            
            if label in [1, 6]:
                target_percent = 0.7
                logger.info(f"Label {label}: Decimating to 70% of original faces.")
            elif label == 2:
                target_percent = 0.7
                logger.info(f"Label {label}: Decimating to 70% of original faces.")
            else:
                target_percent = 0.2
                logger.info(f"Label {label}: Decimating to 20% of original faces.")
            
            target_faces = int(len(mesh.faces) * target_percent)
                
            if len(mesh.faces) > 1000:
                logger.info(f"Decimating label_{label} from {len(mesh.faces)} to {target_faces} faces")
                mesh = mesh.simplify_quadric_decimation(target_faces)
                logger.info(f"Faces after decimation: {len(mesh.faces)}")
            
            # Apply smoothing
            iterations = 10 if label in [1, 2] else 20
            mesh = trimesh.smoothing.filter_laplacian(
                mesh,
                lamb=0.3,
                iterations=iterations,
                volume_constraint=True
            )
            
            logger.info(f"Post-processing bounds for label_{label}: {mesh.bounds}")
            processed_meshes.append((mesh, label))
        
        # Calculate real-world dimensions of processed scene (before final scaling)
        all_processed_vertices = np.vstack([mesh.vertices for mesh, _ in processed_meshes])
        dimensions = np.ptp(all_processed_vertices, axis=0)
        logger.info(f"\nProcessed scene dimensions (real-world units):")
        logger.info(f"X: {dimensions[0]:.2f}")
        logger.info(f"Y: {dimensions[1]:.2f}")
        logger.info(f"Z: {dimensions[2]:.2f}")
        
        # Optional: Scale to convenient size while preserving proportions (from AFFINE version)
        max_dimension = np.max(dimensions)
        if max_dimension > 100:  # arbitrary threshold
            scale_factor = 100 / max_dimension  # scale to 100 units
            scale_matrix = np.eye(4)
            scale_matrix[:3, :3] *= scale_factor
            
            logger.info(f"\nApplying uniform scaling with factor: {scale_factor}")
            logger.info(f"Original max dimension: {max_dimension:.2f}")
            logger.info(f"New max dimension will be: {max_dimension * scale_factor:.2f}")
            
            for mesh, _ in processed_meshes:
                mesh.apply_transform(scale_matrix)
        
        # Calculate overall centroid and scale (original method for final normalization)
        all_processed_vertices = np.vstack([mesh.vertices for mesh, _ in processed_meshes])
        scene_centroid = np.mean(all_processed_vertices, axis=0)
        max_distance = np.max(np.linalg.norm(all_processed_vertices - scene_centroid, axis=1))
        scale = 1.0 / max_distance if max_distance > 0 else 1.0
        
        logger.info(f"\nApplying scaling with factor: {scale}")
        
        # Add mesh to scene with final transformations
        for mesh, label in processed_meshes:
            # Center and scale the mesh (original method)
            mesh.vertices = (mesh.vertices - scene_centroid) * scale
            
            # Add to scene
            scene.add_geometry(mesh, node_name=f'label_{label}')
            logger.info(f"Added scaled mesh as label_{label}")
            logger.info(f"Mesh bounds: {mesh.bounds}")
        
        
        output_path = os.path.join(
            os.path.dirname(filepath),
            f"{os.path.splitext(os.path.basename(filepath))[0].replace('.nii', '')}.glb"
        )
        
        scene.export(output_path)
        logger.info(f"\nExported scaled model to: {output_path}")
        
        if not os.path.exists(output_path):
            raise FileNotFoundError("GLB export failed or file not found")
            
        return output_path
        
    except Exception as e:
        logger.error(f"Error in extract_transformed_mesh: {str(e)}")
        raise

if __name__ == "__main__":
    input_file = "app/static/models/CME_SEG_112.nii.gz"
    output_path = extract_transformed_mesh(input_file)
    print(f"Done: {output_path}")