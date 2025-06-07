import os
import sys
import numpy as np
import nibabel as nib
from skimage.measure import marching_cubes
import trimesh
import logging
import open3d

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def create_rotation_matrix():
    """Create combined rotation matrix for Y(180°), X(-90°), and Z(180°) rotations to correctly orient the mesh for three.js"""
    # Convert angles to radians


    y_angle = 0 # 180 degrees
    x_angle = -np.pi/2  # -90 degrees
    z_angle = -np.pi/1.16  # 180 degrees
    
    # Create rotation matrices
    Ry = np.array([
        [np.cos(y_angle), 0, np.sin(y_angle), 0],
        [0, 1, 0, 0],
        [-np.sin(y_angle), 0, np.cos(y_angle), 0],
        [0, 0, 0, 1]
    ])
    
    Rx = np.array([
        [1, 0, 0, 0],
        [0, np.cos(x_angle), -np.sin(x_angle), 0],
        [0, np.sin(x_angle), np.cos(x_angle), 0],
        [0, 0, 0, 1]
    ])

    Rz = np.array([
        [np.cos(z_angle), -np.sin(z_angle), 0, 0],
        [np.sin(z_angle), np.cos(z_angle), 0, 0],
        [0, 0, 1, 0],
        [0, 0, 0, 1]
    ])
    
    # Combine rotations (Z rotation first, then Y rotation, then X rotation)
    return Rx @ Ry @ Rz

def process_segmentation_test(filepath):
    try:
        logger.info(f"Starting processing of file: {filepath}")
        
        # Extract base filename
        filename = os.path.basename(filepath)
        base_filename = os.path.splitext(filename)[0]
        if base_filename.endswith('.nii'):
            base_filename = os.path.splitext(base_filename)[0]
        
        # Load the NIfTI file
        nifti_img = nib.load(filepath)
        segmentation = nifti_img.get_fdata()
        
        print("\nSegmentation Analysis:")
        print(f"Shape: {segmentation.shape}")
        print(f"Data type: {segmentation.dtype}")
        print(f"Value range: [{segmentation.min()}, {segmentation.max()}]")
        print(f"Unique values: {np.unique(segmentation)}")

        # Get affine transform from NIfTI header
        affine = nifti_img.affine
        voxel_dims = nifti_img.header.get_zooms()
        print(f"\nVoxel dimensions: {voxel_dims}")
        print(f"Affine transform:\n{affine}")

        # Create rotation matrix
        rotation_matrix = create_rotation_matrix()

        # Process each label
        meshes = []
        label_ids = [1, 2, 3, 4, 5, 6]

        # Calculate centroid of all voxels to use as reference point
        all_points = np.array(np.where(segmentation > 0)).T
        if len(all_points) > 0:
            centroid = np.mean(all_points, axis=0)
        else:
            centroid = np.array(segmentation.shape) / 2

        for label_id in label_ids:
            print(f"\nProcessing label {label_id}")
            
            # Create binary mask
            mask = (segmentation == label_id)
            voxel_count = np.sum(mask)
            print(f"Label {label_id}:")
            print(f"  Voxels: {voxel_count}")
            
            if voxel_count == 0:
                print(f"  No voxels found - skipping")
                continue

            try:
                # Extract mesh
                print(f"  Extracting surface...")
                verts, faces, normals, values = marching_cubes(mask)
                print(f"  Surface extracted: {len(verts)} vertices, {len(faces)} faces")
                
                # Apply affine transformation to vertices
                verts_homog = np.hstack((verts, np.ones((len(verts), 1))))
                verts = (affine @ verts_homog.T).T[:, :3]
                
                # Create mesh
                mesh = trimesh.Trimesh(vertices=verts, faces=faces)
                print(f"  Initial mesh:")
                print(f"    Vertices: {len(mesh.vertices)}")
                print(f"    Faces: {len(mesh.faces)}")
                print(f"    Bounds: {mesh.bounds}")
                
                # Flip normals to ensure they are facing outward
                mesh.invert()
                print(f"  Normals flipped to face outward.")
                
                # Determine target face count based on label
                if label_id == 1:
                    target_faces = 140000
                elif label_id == 2:
                    target_faces = 90000
                else:
                    target_faces = 50000

                # Decimate if needed
                if len(mesh.faces) > target_faces:
                    print(f"  Decimating mesh...")
                    original_faces = len(mesh.faces)
                    try:
                        mesh = mesh.simplify_quadric_decimation(target_faces)
                        print(f"    Faces reduced: {original_faces} → {len(mesh.faces)}")
                    except Exception as e:
                        print(f"    Warning: Decimation failed, using original mesh: {str(e)}")

                # Smooth while preserving volume
                iterations = 8 if label_id in [1, 2] else 30
                print(f"  Smoothing with {iterations} iterations...")
                mesh = trimesh.smoothing.filter_laplacian(
                    mesh,
                    lamb=0.5,
                    iterations=iterations,
                    implicit_time_integration=False,
                    volume_constraint=True
                )

                # Store mesh with color
                colors = [
                    [0.976, 0.329, 0.329, 0.8],  # Red
                    [0.051, 0.573, 0.957, 0.8],  # Green
                    [1.000, 0.549, 0.620, 0.8],  # Blue
                    [1.000, 0.843, 0.769, 0.8],  # Yellow
                    [1.000, 0.855, 0.463, 0.8]   # Magenta
                ]
                
                # Assign vertex colors to the mesh
                vertex_colors = np.tile(colors[label_id - 1], (len(mesh.vertices), 1))
                mesh.visual.vertex_colors = vertex_colors
                print(f"  Color applied to mesh.")

                meshes.append({
                    'mesh': mesh,
                    'label': label_id
                })
                print(f"  Mesh {label_id} processed successfully")
                
            except Exception as e:
                print(f"  Error processing label {label_id}: {str(e)}")
                continue

        if not meshes:
            raise ValueError("No meshes were generated!")

        print(f"\nCombining {len(meshes)} meshes...")
        scene = trimesh.Scene()
        
        # Calculate overall centroid of all meshes
        all_vertices = np.vstack([m['mesh'].vertices for m in meshes])
        scene_centroid = np.mean(all_vertices, axis=0)
        
        # Calculate scale while preserving relative positions
        max_distance = np.max(np.linalg.norm(all_vertices - scene_centroid, axis=1))
        scale = 1.0 / max_distance if max_distance > 0 else 1.0
        
        # Add each mesh to scene
        for idx, mesh_data in enumerate(meshes):
            mesh = mesh_data['mesh']
            label = mesh_data['label']
            
            # Center, rotate, and scale mesh while preserving relative positions
            vertices_centered = mesh.vertices - scene_centroid
            vertices_homog = np.hstack((vertices_centered, np.ones((len(vertices_centered), 1))))
            vertices_rotated = (rotation_matrix @ vertices_homog.T).T
            mesh.vertices = vertices_rotated[:, :3] * scale
            
            print(f"\nAdding mesh {label} to scene:")
            print(f"  Vertices: {len(mesh.vertices)}")
            print(f"  Faces: {len(mesh.faces)}")
            print(f"  Bounds: {mesh.bounds}")
            
            # Add to scene with explicit name
            scene.add_geometry(mesh, node_name=f'label_{label}')

        # Export scene
        output_file = f'{base_filename}.glb'
        output_path = os.path.join(os.path.dirname(filepath), output_file)
        print(f"\nExporting to: {output_path}")
        scene.export(output_path)
        
        # Verify the exported file
        print("\nVerifying exported file...")
        exported_scene = trimesh.load(output_path)
        print(f"Number of meshes in exported scene: {len(exported_scene.geometry)}")
        for name, geom in exported_scene.geometry.items():
            print(f"\nMesh: {name}")
            print(f"  Vertices: {len(geom.vertices)}")
            print(f"  Faces: {len(geom.faces)}")
            print(f"  Bounds: {geom.bounds}")
        
        return output_path

    except Exception as e:
        print(f"Error: {str(e)}")
        raise

if __name__ == "__main__":
    if len(sys.argv) > 1:
        input_file = sys.argv[1]
    else:
        input_file = "app/static/models/CME_SEG_065.nii.gz"
    
    process_segmentation_test(input_file)
