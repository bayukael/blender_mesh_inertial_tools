bl_info = {
    "name": "Inertial Parameters Calculator",
    "blender": (4, 0, 0),
    "category": "Object",
}

import bpy
import mathutils

class ObjectSelectMeshesInSelected(bpy.types.Operator):
    bl_idname = "object.select_meshes_in_selected"
    bl_label = "Mesh Selector"
    bl_description = "Select all meshes that are included in the selected objects"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        if not context.selected_objects: # if 
            self.report({'INFO'}, f"No object is selected")
            return {'FINISHED'}
        selected_names = [obj.name for obj in context.selected_objects]
        meshes = select_all_meshes_from_predefined_list(selected_names)
        meshes_names = [obj.name for obj in meshes]
        context.scene["stored_objects_names"] = selected_names
        context.scene["stored_meshes_names"] = meshes_names
        self.report({'INFO'}, f"Stored {len(selected_names)} selected object(s).")
        return {'FINISHED'}

class ObjectReselectRecentSelection(bpy.types.Operator):
    bl_idname = "object.reselect_recent_selection"
    bl_label = "Reselect Previous Selection"
    bl_description = "Reselect objects that has been selected previously"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        stored_names = context.scene.get("stored_objects_names", [])
        bpy.ops.object.select_all(action='DESELECT')
        for name in stored_names:
            obj = bpy.data.objects.get(name)
            if obj:
                obj.select_set(True)
        self.report({'INFO'}, f"Restored {len(stored_names)} object(s).")
        return {'FINISHED'}

class ObjectCombineMesh(bpy.types.Operator):
    bl_idname = "object.combine_mesh"
    bl_label = "Mesh Combiner"
    bl_description = "Combine several meshes into one single mesh and move it into a collection"
    bl_options = {'REGISTER', 'UNDO'}
    
    mesh_collection: bpy.props.StringProperty(name="Collection name", default="combined_meshes")
    mesh_name: bpy.props.StringProperty(name="Mesh name")
    
    def execute(self, context):
        objects_names = context.scene.get("stored_objects_names", [])
        meshes_storage_name = self.mesh_collection
        combined_mesh_name = self.mesh_name
        
        if meshes_storage_name in bpy.data.collections:
            meshes_storage = bpy.data.collections[meshes_storage_name]
        else:
            meshes_storage = bpy.data.collections.new(meshes_storage_name)
            bpy.context.scene.collection.children.link(meshes_storage)
            
        combined_mesh = combine_meshes_from_predefined_list(objects_names, combined_mesh_name, True, meshes_storage)
        combined_mesh_real_name = combined_mesh.name # Get the actual name because Blender might add some suffix to avoid naming duplicates
        
        self.report({'INFO'}, f"self.mesh_collection:'{self.mesh_collection}' mesh_name:'{combined_mesh_real_name}'.")
        return {'FINISHED'}
    
    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

class ObjectCombineComputeMeshInertialParams(bpy.types.Operator):
    bl_idname = "object.combine_and_compute_mesh_inertial_params"
    bl_label = "Mesh Combine and Compute"
    bl_description = "Combine meshes and compute its inertial parameters"
    bl_options = {'REGISTER', 'UNDO'}
    
    mesh_collection: bpy.props.StringProperty(name="Collection name", default="meshes_to_calculate")
    mesh_name: bpy.props.StringProperty(name="Mesh name")
    mesh_mass: bpy.props.FloatProperty(name="Mesh mass (grams)")
    voxel_size: bpy.props.FloatProperty(name="Voxel size (mm)", default=0.002)
    
    def execute(self, context):
        objects_names = context.scene.get("stored_objects_names", [])
        meshes_storage_name = self.mesh_collection
        combined_mesh_name = self.mesh_name
        combined_mesh_mass = self.mesh_mass
        voxel_size = self.voxel_size
        
        if meshes_storage_name in bpy.data.collections:
            meshes_storage = bpy.data.collections[meshes_storage_name]
        else:
            meshes_storage = bpy.data.collections.new(meshes_storage_name)
            bpy.context.scene.collection.children.link(meshes_storage)
            
        combined_mesh = combine_meshes_from_predefined_list(objects_names, combined_mesh_name, True, meshes_storage)
        combined_mesh_real_name = combined_mesh.name # Get the actual name because Blender might add some suffix to avoid naming duplicates
        apply_transform(combined_mesh_real_name) # So that all transformation data stored in the object are applied to its matrix_world
        set_origin_to_world_origin(combined_mesh_real_name) # So that the inertial tensor is computed w.r.t. world origin
        create_voxels_from_mesh(combined_mesh_real_name, voxel_size)
        
        inertial_params = integrate_voxel_inertial_tensor(combined_mesh_real_name, combined_mesh_mass)

        combined_mesh["mesh_Ixx_kgm2"] = inertial_params[0]
        combined_mesh["mesh_Iyy_kgm2"] = inertial_params[1]
        combined_mesh["mesh_Izz_kgm2"] = inertial_params[2]
        combined_mesh["mesh_Ixy_kgm2"] = inertial_params[3]
        combined_mesh["mesh_Ixz_kgm2"] = inertial_params[4]
        combined_mesh["mesh_Iyz_kgm2"] = inertial_params[5]
        combined_mesh["mesh_com_x"] = inertial_params[6]
        combined_mesh["mesh_com_y"] = inertial_params[7]
        combined_mesh["mesh_com_z"] = inertial_params[8]
        combined_mesh["mesh_mass_in_gr"] = inertial_params[9]
        
        self.report({'INFO'}, f"self.mesh_collection:'{self.mesh_collection}' mesh_name:'{combined_mesh_real_name}'.")
        return {'FINISHED'}
    
    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

class ObjectRecomputeMeshInertialParams(bpy.types.Operator):
    bl_idname = "object.compute_mesh_inertial_params"
    bl_label = "Recompute Inertial Params"
    bl_description = "Recompute mesh inertial parameters"
    bl_options = {'REGISTER', 'UNDO'}
    
    mesh_mass: bpy.props.FloatProperty(name="Mesh mass (grams)")
    
    def execute(self, context):
        if len(context.selected_objects) != 1: # if 
            self.report({'INFO'}, f"Please select a mesh first. Don't select multiple meshes.")
            return {'FINISHED'}
        mesh_obj = context.selected_objects[0]
        if mesh_obj.type != 'MESH':
            self.report({'INFO'}, f"The selected object is not a mesh. Ignored.")
            return {'FINISHED'}
        inertial_params = integrate_voxel_inertial_tensor(mesh_obj.name, self.mesh_mass)

        mesh_obj["mesh_Ixx_kgm2"] = inertial_params[0]
        mesh_obj["mesh_Iyy_kgm2"] = inertial_params[1]
        mesh_obj["mesh_Izz_kgm2"] = inertial_params[2]
        mesh_obj["mesh_Ixy_kgm2"] = inertial_params[3]
        mesh_obj["mesh_Ixz_kgm2"] = inertial_params[4]
        mesh_obj["mesh_Iyz_kgm2"] = inertial_params[5]
        mesh_obj["mesh_com_x"] = inertial_params[6]
        mesh_obj["mesh_com_y"] = inertial_params[7]
        mesh_obj["mesh_com_z"] = inertial_params[8]
        mesh_obj["mesh_mass_in_gr"] = inertial_params[9]
        
        return {'FINISHED'}
    
    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)
    

class ObjectComputeCollectionInertialParams(bpy.types.Operator):
    bl_idname = "object.compute_collection_inertial_params"
    bl_label = "Compute Collection Inertial Params"
    bl_description = "Compute inertial parameters of the whole meshes together that reside in the selected collection"
    bl_options = {'REGISTER', 'UNDO'}
        
    def execute(self, context):
        num_of_selected_objects = len(context.selected_ids)
        if num_of_selected_objects != 1:
            self.report({'INFO'}, "Please select a collection that contains meshes and their inertial parameters.")
            return {'FINISHED'}
        
        selected_id = context.selected_ids[0]        
        if not isinstance(selected_id, bpy.types.Collection):
            self.report({'INFO'}, "You did not select a collection...")
            return {'FINISHED'}
        
        # COMPUTE TOTAL MASS IN GRAMS
        total_mass = 0.0
        for obj in selected_id.all_objects:
            total_mass += obj.get("mesh_mass_in_gr")
        
        # FIND CENTER OF MASS
        com_x = 0.0
        com_y = 0.0
        com_z = 0.0
        for obj in selected_id.all_objects:
            mesh_com_x = obj.get("mesh_com_x")
            mesh_com_y = obj.get("mesh_com_y")
            mesh_com_z = obj.get("mesh_com_z")
            mesh_mass = obj.get("mesh_mass_in_gr")
            com_x += (mesh_com_x * mesh_mass / total_mass)
            com_y += (mesh_com_y * mesh_mass / total_mass)
            com_z += (mesh_com_z * mesh_mass / total_mass)
        
        Ixx = 0
        Iyy = 0
        Izz = 0
        Ixy = 0
        Ixz = 0
        Iyz = 0
        for obj in selected_id.all_objects:
            # OBTAIN OBJECT'S INERTIAL PARAMETERS
            mesh_Ixx_kgm2 = obj.get("mesh_Ixx_kgm2")
            mesh_Iyy_kgm2 = obj.get("mesh_Iyy_kgm2")
            mesh_Izz_kgm2 = obj.get("mesh_Izz_kgm2")
            mesh_Ixy_kgm2 = obj.get("mesh_Ixy_kgm2")
            mesh_Ixz_kgm2 = obj.get("mesh_Ixz_kgm2")
            mesh_Iyz_kgm2 = obj.get("mesh_Iyz_kgm2")
            mesh_com_x = obj.get("mesh_com_x")
            mesh_com_y = obj.get("mesh_com_y")
            mesh_com_z = obj.get("mesh_com_z")
            mesh_mass_in_kg = obj.get("mesh_mass_in_gr") / 1000.0 # Convert from gr to Kg
            
            # COMPUTE OBJECT'S NEW INERTIAL TENSOR W.R.T THE CENTER OF MASS OF THE COMBINED OBJECTS
            delta_x = com_x - mesh_com_x
            delta_y = com_y - mesh_com_y
            delta_z = com_z - mesh_com_z
            mesh_new_Ixx = mesh_Ixx_kgm2 + mesh_mass_in_kg * (delta_y**2 + delta_z**2)
            mesh_new_Iyy = mesh_Iyy_kgm2 + mesh_mass_in_kg * (delta_x**2 + delta_z**2)
            mesh_new_Izz = mesh_Izz_kgm2 + mesh_mass_in_kg * (delta_x**2 + delta_y**2)
            mesh_new_Ixy = mesh_Ixy_kgm2 - mesh_mass_in_kg * delta_x * delta_y
            mesh_new_Ixz = mesh_Ixz_kgm2 - mesh_mass_in_kg * delta_x * delta_z
            mesh_new_Iyz = mesh_Iyz_kgm2 - mesh_mass_in_kg * delta_y * delta_z
            
            # ADD ALL OBJECT'S NEW INERTIAL TENSOR
            Ixx += mesh_new_Ixx
            Iyy += mesh_new_Iyy
            Izz += mesh_new_Izz
            Ixy += mesh_new_Ixy
            Ixz += mesh_new_Ixz
            Iyz += mesh_new_Iyz
        
        sdf_inertial_text = f"""
<inertial>
    <pose>{com_x} {com_y} {com_z}        0 0 0</pose>
    <mass>{total_mass/1000.0}</mass>
    <inertia>
        <ixx>{Ixx}</ixx>
        <iyy>{Iyy}</iyy>
        <izz>{Izz}</izz>
        <ixy>{Ixy}</ixy>
        <ixz>{Ixz}</ixz>
        <iyz>{Iyz}</iyz>
    </inertia>
</inertial>
        """
        print(sdf_inertial_text)
        
        selected_id["Total Ixx"] = Ixx
        selected_id["Total Iyy"] = Iyy
        selected_id["Total Izz"] = Izz
        selected_id["Total Ixy"] = Ixy
        selected_id["Total Ixz"] = Ixz
        selected_id["Total Iyz"] = Iyz
        selected_id["Center of Mass"] = [com_x, com_y, com_z]
        selected_id["Total Mass"] = total_mass
        
        return {'FINISHED'}

addon_keymaps = []

def register():
    bpy.utils.register_class(ObjectSelectMeshesInSelected)
    bpy.utils.register_class(ObjectReselectRecentSelection)
    bpy.utils.register_class(ObjectCombineMesh)
    bpy.utils.register_class(ObjectCombineComputeMeshInertialParams)
    bpy.utils.register_class(ObjectComputeCollectionInertialParams)
    bpy.utils.register_class(ObjectRecomputeMeshInertialParams)
    
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
    if kc:
        km = wm.keyconfigs.addon.keymaps.new(name='Outliner', space_type='OUTLINER')
        
        kmi = km.keymap_items.new(ObjectSelectMeshesInSelected.bl_idname, 'M', 'PRESS', alt=True)
        addon_keymaps.append((km, kmi))
        
        kmi = km.keymap_items.new(ObjectReselectRecentSelection.bl_idname, 'N', 'PRESS', alt=True)
        addon_keymaps.append((km, kmi))
        
        kmi = km.keymap_items.new(ObjectCombineMesh.bl_idname, 'J', 'PRESS', shift=True)
        addon_keymaps.append((km, kmi))
        
        kmi = km.keymap_items.new(ObjectCombineComputeMeshInertialParams.bl_idname, 'J', 'PRESS', alt=True)
        addon_keymaps.append((km, kmi))
        
        kmi = km.keymap_items.new(ObjectComputeCollectionInertialParams.bl_idname, 'U', 'PRESS', alt=True)
        addon_keymaps.append((km, kmi))
        
        kmi = km.keymap_items.new(ObjectRecomputeMeshInertialParams.bl_idname, 'Y', 'PRESS', alt=True)
        addon_keymaps.append((km, kmi))
    
def unregister():
	# Remove the hotkey
    for km, kmi in addon_keymaps:
        km.keymap_items.remove(kmi)
    addon_keymaps.clear()
    
    bpy.utils.unregister_class(ObjectSelectMeshesInSelected)
    bpy.utils.unregister_class(ObjectReselectRecentSelection)
    bpy.utils.unregister_class(ObjectCombineMesh)
    bpy.utils.unregister_class(ObjectCombineComputeMeshInertialParams)
    bpy.utils.unregister_class(ObjectComputeCollectionInertialParams)
    bpy.utils.unregister_class(ObjectRecomputeMeshInertialParams)

def select_all_meshes_from_predefined_list(the_list):
    bpy.ops.object.select_all(action='DESELECT')  # Deselect everything first
    mesh_children = []
    for an_entry in the_list:
        obj = bpy.data.objects.get(an_entry)
        if obj is None:
            print(f"Object {obj.name} not found. Continuing...")
            continue
        print(f"Selecting meshes inside {obj.name}...")
        for child in obj.children_recursive:
            if child.type == 'MESH':
                mesh_children.append(child)
                child.select_set(True)
                
    print("All meshes in the list are selected")
    return mesh_children
    
def copy_and_prepare(obj, place_to_store):
    # Duplicate the object itself
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    new_obj = obj.copy()
    
    # Duplicate the mesh data as well (makes it independent)
    new_obj.data = obj.data.copy()

    # Copy transformation matrix
    mat_world_copy = obj.matrix_world.copy()

    new_obj.name = f"{obj.name}_COPY"
    
    new_obj.parent = None # To make the copied object totally independent from the parent's transformation
    new_obj.matrix_world = mat_world_copy # To make the copied object stays at place with respect to the world coordinates

    # Link to the specified collection
    place_to_store.objects.link(new_obj)
    
    return new_obj

def copy_multiple_meshes(mesh_objects, collection): # copy [mesh_objects] into the specified [collection]
    total = len(mesh_objects)
    print(f"Preparing to copy {total} mesh object(s)...")

    copies = []
    for i, obj in enumerate(mesh_objects, start=1):
        print(f"Copying [{i}/{total}]: {obj.name}")
        new_obj = copy_and_prepare(obj, collection)
        copies.append(new_obj)

    print("All objects have been copied.")
    return copies

def move_multiple_meshes(mesh_objects, collection):
    total = len(mesh_objects)
    print(f"Preparing to move {total} mesh object(s)...")

    moved_objects = []
    for i, obj in enumerate(mesh_objects, start=1):
        print(f"Moving [{i}/{total}]: {obj.name}")
        mat_world_copy = obj.matrix_world.copy()
        obj.parent = None
        obj.matrix_world = mat_world_copy
        for current_collection in obj.users_collection:
            current_collection.objects.unlink(obj)
        collection.objects.link(obj)
        moved_objects.append(obj)

    print("All objects have been moved.")
    return moved_objects

def join_meshes(meshes_to_join, new_name="JoinedMesh"):
    # Deselect everything
    bpy.ops.object.select_all(action='DESELECT')
        
    # Select all objects to join
    for obj in meshes_to_join:
        obj.select_set(True)
    
    # Set one active object (needed for joining)
    bpy.context.view_layer.objects.active = meshes_to_join[0]
    print(f"Joining meshes into \"{new_name}\"")
    # Perform join operation
    bpy.ops.object.join()

    # Rename the joined object
    joined_obj = bpy.context.active_object
    joined_obj.name = new_name
    print(f"Joined object created: {joined_obj.name}")
    return joined_obj

def combine_meshes_from_predefined_list(the_list, combined_mesh_name: str, use_move: bool, meshes_storage):
    meshes = select_all_meshes_from_predefined_list(the_list)
    if use_move is True:
        meshes_to_work_on = move_multiple_meshes(meshes, meshes_storage)
    else:
        meshes_to_work_on = copy_multiple_meshes(meshes, meshes_storage)
    combined_mesh = join_meshes(meshes_to_work_on, combined_mesh_name)
    return combined_mesh

def set_origin_to_world_origin(obj_name: str):
    # Store the current 3D cursor location
    obj = bpy.data.objects.get(obj_name)
    if obj is None:
        raise ValueError(f"Object '{obj_name}' not found.")
    original_cursor_location = bpy.context.scene.cursor.location.copy()

    # Move 3D cursor to world origin
    bpy.context.scene.cursor.location = (0.0, 0.0, 0.0)

    # Deselect all, select the object
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj

    # Set origin to 3D cursor
    bpy.ops.object.origin_set(type='ORIGIN_CURSOR', center='MEDIAN')

    # Restore original cursor position
    bpy.context.scene.cursor.location = original_cursor_location

    print(f"Origin of '{obj.name}' set to world origin. Cursor restored.")

def apply_transform(obj_name: str):
    # Get the object
    obj = bpy.data.objects.get(obj_name)
    if obj is None:
        raise ValueError(f"Object '{obj_name}' not found.")
    # Apply the location change
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.transform_apply(isolate_users=True)  # Apply object transforms (so geometry is unchanged)

def create_voxels_from_mesh(obj_name: str, voxel_size: float = 1.0):
    """
    Creates a Geometry Nodes modifier on the specified object:
    1. Converts a mesh to a volume using voxel_size.
    2. Distributes points in the volume on a grid.
    3. Convert the points into vertices and output them
    """
    # Get the object
    obj = bpy.data.objects.get(obj_name)
    if obj is None:
        raise ValueError(f"Object '{obj_name}' not found.")
    
    modifier_name = "MeshToPoints"
    if obj and modifier_name in obj.modifiers:
        obj.modifiers.remove(obj.modifiers[modifier_name])
        
    node_group_name = "MeshToPointsGroup"
    if node_group_name in bpy.data.node_groups:
        node_group = bpy.data.node_groups[node_group_name]
    else:
        node_group = bpy.data.node_groups.new(name="MeshToPointsGroup", type='GeometryNodeTree')
    
    gnmod = obj.modifiers.new(modifier_name, "NODES")
    
    # Add input socket (Geometry)
    node_group.interface.new_socket(name="Geometry", socket_type='NodeSocketGeometry', in_out='INPUT')
    
    # Add output socket (Geometry)
    node_group.interface.new_socket(name="Geometry", socket_type='NodeSocketGeometry', in_out='OUTPUT')
    # Add input/output nodes
    # Create group I/O nodes
    in_node = node_group.nodes.new("NodeGroupInput")
    in_node.location = (-600, 0)

    out_node = node_group.nodes.new("NodeGroupOutput")
    out_node.location = (600, 0)

    # Mesh to Volume
    mesh_to_volume = node_group.nodes.new("GeometryNodeMeshToVolume")
    mesh_to_volume.location = (-400, 0)
    mesh_to_volume.resolution_mode = 'VOXEL_SIZE'
    mesh_to_volume.inputs["Density"].default_value = 1000.0 # The documentation is not clear on this. So this value is just an arbitrary value and so far it looks good.
    mesh_to_volume.inputs["Voxel Size"].default_value = voxel_size

    # Distribute Points in Volume
    distribute = node_group.nodes.new("GeometryNodeDistributePointsInVolume")
    distribute.location = (0, 0)
    distribute.mode = 'DENSITY_GRID'
    distribute.inputs["Spacing"].default_value = (voxel_size, voxel_size, voxel_size)  # Adjust as needed
    
    # Points to Vertices
    points_to_vertices = node_group.nodes.new("GeometryNodePointsToVertices")
    points_to_vertices.location = (400, 0)


#    # Wire it all up
    links = node_group.links
    links.new(in_node.outputs["Geometry"], mesh_to_volume.inputs["Mesh"])
    links.new(mesh_to_volume.outputs["Volume"], distribute.inputs["Volume"])
    links.new(distribute.outputs["Points"], points_to_vertices.inputs["Points"])
    links.new(points_to_vertices.outputs["Mesh"], out_node.inputs["Geometry"])
    
#    # Link input to output
    gnmod.node_group = node_group
    print("Geometry nodes for voxelizing mesh is created.")
# ----------------------------------------------------------------------------------

def integrate_voxel_inertial_tensor(obj_name: str, mass_in_gr: float, use_centroid: bool = True ): 
    obj = bpy.data.objects.get(obj_name)
    if obj is None:
        raise ValueError(f"Object '{obj_name}' not found.")
        
    depsgraph = bpy.context.evaluated_depsgraph_get()
    eval_obj = obj.evaluated_get(depsgraph)
    
    # Access the evaluated geometry from the modifier
    mesh = eval_obj.to_mesh()
    num_of_voxels = len(mesh.vertices)
    voxel_mass = mass_in_gr / num_of_voxels
    
    object_centroid_x = 0.0
    object_centroid_y = 0.0
    object_centroid_z = 0.0
    if use_centroid is True:
        print("Using Object's Centroid...")
        for i, vert in enumerate(mesh.vertices):
            object_centroid_x += vert.co.x/num_of_voxels
            object_centroid_y += vert.co.y/num_of_voxels
            object_centroid_z += vert.co.z/num_of_voxels
    bpy.context.scene.cursor.location = (object_centroid_x, object_centroid_y, object_centroid_z)
    
    print(f"Number of voxels: {num_of_voxels}")
    Ixx = 0
    Iyy = 0
    Izz = 0
    Ixy = 0
    Ixz = 0
    Iyz = 0
    for i, vert in enumerate(mesh.vertices):
        x = vert.co.x - object_centroid_x
        y = vert.co.y - object_centroid_y
        z = vert.co.z - object_centroid_z
        Ixx += voxel_mass * (y**2 + z**2)
        Iyy += voxel_mass * (x**2 + z**2)
        Izz += voxel_mass * (x**2 + y**2)
        Ixy += -voxel_mass * x * y
        Ixz += -voxel_mass * x * z
        Iyz += -voxel_mass * y * z
    
    Ixx = Ixx / 1000.0 # Convert to Kg.m^2
    Iyy = Iyy / 1000.0 # Convert to Kg.m^2
    Izz = Izz / 1000.0 # Convert to Kg.m^2
    Ixy = Ixy / 1000.0 # Convert to Kg.m^2
    Ixz = Ixz / 1000.0 # Convert to Kg.m^2
    Iyz = Iyz / 1000.0 # Convert to Kg.m^2

    inertial_parameters = (Ixx, Iyy, Izz, Ixy, Ixz, Iyz, object_centroid_x, object_centroid_y, object_centroid_z, mass_in_gr)
    
    # Optional: free the mesh to avoid memory leak
    eval_obj.to_mesh_clear()
    
    return inertial_parameters

######################## THE CODE STARTS HERE ########################

if __name__ == "__main__":
    register()

######################## THE CODE ENDS HERE ########################
