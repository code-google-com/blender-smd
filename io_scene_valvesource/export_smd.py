#  Copyright (c) 2013 Tom Edwards contact@steamreview.org
#
# ##### BEGIN GPL LICENSE BLOCK #####
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# ##### END GPL LICENSE BLOCK #####

import bpy, bmesh, subprocess
from bpy import ops
from mathutils import *
from math import *

from .utils import *
from . import datamodel

wm = bpy.types.WindowManager
if not 'progress_begin' in dir(wm): # instead of requiring 2.67
	wm.progress_begin = wm.progress_update = wm.progress_end = lambda *args: None

class SMD_OT_Compile(bpy.types.Operator, Logger):
	bl_idname = "smd.compile_qc"
	bl_label = "Compile QC"
	bl_description = "Compile QCs with the Source SDK"

	filepath = bpy.props.StringProperty(name="File path", description="QC to compile", maxlen=1024, default="", subtype='FILE_PATH')
	
	@classmethod
	def poll(self,context):
		return len(p_cache.qc_paths) > 0 and gamePathValid() and studiomdlPathValid()

	def execute(self,context):
		num = self.compileQCs(self.properties.filepath)
		#if num > 1:
		#	bpy.context.window_manager.progress_begin(0,1)
		if not self.properties.filepath:
			self.properties.filepath = "QC"
		self.errorReport("compiled","{} QC".format(getEngineBranchName()),self, num)
		bpy.context.window_manager.progress_end()
		return {'FINISHED'}
	
	@classmethod
	def getQCs(self,path = None):
		import glob
		ext = ".qc"
		out = []
		internal = False
		if not path:
			path = bpy.path.abspath(bpy.context.scene.smd_qc_path)
			internal = True
		for result in glob.glob(path):
			if result.endswith(ext):
				out.append(result)

		if not internal and not len(out) and not path.endswith(ext):
			out = getQCs(path + ext)
		return out
	
	def compileQCs(self,path=None):
		scene = bpy.context.scene
		print("\n")

		studiomdl_path = os.path.join(bpy.path.abspath(scene.smd_studiomdl_custom_path),"studiomdl.exe")

		if path:
			p_cache.qc_paths = [path]
		else:
			p_cache.qc_paths = SMD_OT_Compile.getQCs()
		num_good_compiles = 0
		if len( p_cache.qc_paths ) == 0:
			self.error("Cannot compile, no QCs provided. The SMD Tools do not generate QCs.")
		elif not os.path.exists(studiomdl_path):
			self.error( "Could not execute studiomdl from \"{}\"".format(studiomdl_path) )
		else:
			i = 0
			num_qcs = len(p_cache.qc_paths)
			for qc in p_cache.qc_paths:
				bpy.context.window_manager.progress_update((i+1) / (num_qcs+1))
				# save any version of the file currently open in Blender
				qc_mangled = qc.lower().replace('\\','/')
				for candidate_area in bpy.context.screen.areas:
					if candidate_area.type == 'TEXT_EDITOR' and candidate_area.spaces[0].text and candidate_area.spaces[0].text.filepath.lower().replace('\\','/') == qc_mangled:
						oldType = bpy.context.area.type
						bpy.context.area.type = 'TEXT_EDITOR'
						bpy.context.area.spaces[0].text = candidate_area.spaces[0].text
						ops.text.save()
						bpy.context.area.type = oldType
						break #what a farce!
				
				print( "Running studiomdl for \"{}\"...\n".format(os.path.basename(qc)) )
				studiomdl = subprocess.Popen([studiomdl_path, "-nop4", "-game", getGamePath(), qc])
				studiomdl.communicate()

				if studiomdl.returncode == 0:
					num_good_compiles += 1
				else:
					self.error("Compile of {}.qc failed. Check the console for details".format(os.path.basename(qc)))
				i+=1
		return num_good_compiles

class SmdExporter(bpy.types.Operator, Logger):
	'''Export SMD or DMX files and compile them with QC scripts'''
	bl_idname = "export_scene.smd"
	bl_label = "Export SMD/VTA/DMX"
	
	directory = bpy.props.StringProperty(name="Export root", description="The root folder into which SMDs from this scene are written", subtype='DIR_PATH')	
	filename = bpy.props.StringProperty(default="", options={'HIDDEN'})

	exportMode_enum = (
		('NONE','No mode','The user will be prompted to choose a mode'),
		('SINGLE','Active','Only the active object'),
		('SINGLE_ANIM','Current action',"Exports the active Armature's current Action"),
		('MULTI','Selection','All selected objects'),
		('SCENE','Scene','Export the objects and animations selected in Scene Properties'),
		)
	exportMode = bpy.props.EnumProperty(items=exportMode_enum,options={'HIDDEN'})
	groupIndex = bpy.props.IntProperty(default=-1,options={'HIDDEN'})

	def execute(self, context):
		props = self.properties
		#bpy.context.window_manager.progress_begin(0,1)

		if props.exportMode == 'NONE':
			self.report({'ERROR'},"bpy.ops.{} requires an exportMode".format(SmdExporter.bl_idname))
			return {'CANCELLED'}
			
		if context.scene.smd_format == 'DMX':
			datamodel.check_support("binary",DatamodelEncodingVersion())
			
			if DatamodelEncodingVersion() < 5 and DatamodelFormatVersion() > 15:
				self.report({'ERROR'},"DMX format \"Model {}\" requires DMX encoding \"Binary 5\" or later".format(DatamodelFormatVersion()))
				return {'CANCELLED' }

		# Handle export root path
		if len(props.directory):
			# We've got a file path from the file selector (or direct invocation)
			context.scene['smd_path'] = props.directory
		else:
			# Get a path from the scene object
			export_root = context.scene.get("smd_path")

			# No root defined, pop up a file select
			if not export_root:
				props.filename = "*** [Please choose a root folder for exports from this scene] ***"
				context.window_manager.fileselect_add(self)
				return {'RUNNING_MODAL'}

			if export_root.startswith("//") and not bpy.context.blend_data.filepath:
				self.report({'ERROR'},"Relative scene output path, but .blend not saved")
				return {'CANCELLED'}

			if export_root[-1] not in ['\\','/']: # append trailing slash
				export_root += os.path.sep		

			props.directory = export_root
		
		# Creating an undo level from edit mode is buggy in 2.64a
		prev_mode = None
		if bpy.context.active_object:
			prev_mode = bpy.context.mode.split("_")[0]
			ops.object.mode_set(mode='OBJECT')
		
		ops.ed.undo_push(message=self.bl_label)
		
		try:
			bpy.context.tool_settings.use_keyframe_insert_auto = False
			bpy.context.tool_settings.use_keyframe_insert_keyingset = False
			
			if props.exportMode == 'SINGLE_ANIM': # really hacky, hopefully this will stay a one-off!
				if context.active_object.type == 'ARMATURE':
					context.active_object.data.smd_action_selection = 'CURRENT'
				props.exportMode = 'SINGLE'

			print("\nSMD EXPORTER RUNNING")

			self.validObs = getValidObs()
			
			# lots of operators only work on visible objects
			for object in bpy.context.scene.objects:
				object.hide = False
			bpy.context.scene.layers = [True] * len(bpy.context.scene.layers)

			# check export mode and perform appropriate jobs
			self.countSMDs = self.attemptedExports = 0
			if props.exportMode == 'SINGLE':
				ob = context.active_object
				group_name = None
				if props.groupIndex != -1:
					# handle the selected object being in a group, but disabled
					try:
						group_name = ob.users_group[props.groupIndex].name
						for g_ob in ob.users_group[props.groupIndex].objects:
							if g_ob.smd_export:
								ob = g_ob
								break
							else:
								ob = None
					except IndexError:
						pass # Blender saved settings from a previous run, doh!

				if ob:
					self.exportObject(context,context.active_object,groupIndex=props.groupIndex)
				else:
					self.error("The group \"" + group_name + "\" has no active objects")
					return {'CANCELLED'}


			elif props.exportMode == 'MULTI':
				exported_groups = []
				for object in context.selected_objects:
					if object.type in mesh_compatible:
						if object.users_group:
							if object.smd_export:
								for i in range(len(object.users_group)):
									if object.users_group[i] not in exported_groups:
										exported_groups.append(object.users_group[i])
										self.exportObject(context,object,groupIndex=i)
						else:
							self.exportObject(context,object)
					elif object.type == 'ARMATURE':
						self.exportObject(context,object)

			elif props.exportMode == 'SCENE':
				for group in bpy.data.groups:
					group_objects = group.objects[:] # avoid pollution from the baking process
					if shouldExportGroup(group):
						for object in group_objects:
							if object.smd_export and object in self.validObs and object.type != 'ARMATURE':
								g_index = -1
								for i in range(len(object.users_group)):
									if object.users_group[i] == group:
										g_index = i
										break
								self.exportObject(context,object,groupIndex=g_index)
								break # only export the first valid object
				for object in getValidObs():
					if object.smd_export:
						should_export = True
						if object.users_group and object.type != 'ARMATURE':
							for group in object.users_group:
								if not group.smd_mute:
									should_export = False
									break
						if should_export:
							self.exportObject(context,object)

			jobMessage = "exported"

			if self.attemptedExports == 0:
				self.error("Found no valid objects for export")
			elif context.scene.smd_qc_compile and context.scene.smd_qc_path:
				# ...and compile the QC
				if not SMD_OT_Compile.poll(context):
					print("Skipping QC compile step: context incorrect\n")
				else:
					num_good_compiles = SMD_OT_Compile.compileQCs(self)
					jobMessage += " and {} QC{} compiled ({}/{})".format(num_good_compiles, "" if num_good_compiles == 1 else "s", getEngineBranchName(), os.path.basename(getGamePath()))
					print("\n")
				
			self.errorReport(jobMessage,"file",self,self.countSMDs)
		finally:
			# Clean everything up
			ops.ed.undo_push(message=self.bl_label)
			ops.ed.undo()
			
			if prev_mode:
				ops.object.mode_set(mode=prev_mode)
			
			props.directory = ""
			props.groupIndex = -1
			
			bpy.context.window_manager.progress_end()

		return {'FINISHED'}

	# indirection to support batch exporting
	def exportObject(self,context,object,groupIndex=-1):
		props = self.properties
		self.attemptedExports += 1

		if groupIndex == -1:
			if not object in self.validObs:
				return
		else:
			if len(set(self.validObs).intersection( set(object.users_group[groupIndex].objects) )) == 0:
				return
				
		# handle subfolder
		if len(object.smd_subdir) == 0 and object.type == 'ARMATURE':
			object.smd_subdir = "anims"
		object.smd_subdir = object.smd_subdir.lstrip("/") # don't want //s here!

		if object.type == 'ARMATURE' and not object.animation_data:
			return; # otherwise we create a folder but put nothing in it

		# assemble filename
		path = os.path.join( bpy.path.abspath(os.path.dirname(props.directory)), object.smd_subdir)
		if not os.path.exists(path):
			try:
				os.makedirs(path)
			except Exception as err:
				self.error("Could not create export folder. Python reports: {}".format(err))
				return

		if object.type in mesh_compatible:
			if groupIndex == -1: path = os.path.join(path,getObExportName(object))
			else: path = os.path.join(path,object.users_group[groupIndex].name)
			
			if self.writeSMD(object, groupIndex, path + getFileExt()):
				self.countSMDs += 1
			if bpy.context.scene.smd_format == 'SMD' and hasShapes(object,groupIndex): # DMX will export mesh and shapes to the same file
				if self.writeSMD(object, groupIndex, path + getFileExt(flex=True), FLEX):
					self.countSMDs += 1
		elif object.type == 'ARMATURE':
			ad = object.animation_data
			
			if object.data.smd_action_selection == 'FILTERED':
				for action in bpy.data.actions:
					if action.users and (not object.smd_action_filter or action.name.lower().find(object.smd_action_filter.lower()) != -1):
						ad.action = action
						if self.writeSMD(object, -1, os.path.join(path, action.name + getFileExt() ), ANIM):
							self.countSMDs += 1
			elif object.animation_data:
				if ad.action:
					if self.writeSMD(object,-1, os.path.join(path, ad.action.name + getFileExt() ), ANIM):
						self.countSMDs += 1
				elif len(ad.nla_tracks):
					nla_actions = []
					for track in ad.nla_tracks:
						if not track.mute:
							for strip in track.strips:
								if not strip.mute and strip.action not in nla_actions:
									nla_actions.append(strip.action)
									ad.action = strip.action
									if self.writeSMD(object,-1,os.path.join(path, ad.action.name + getFileExt()), ANIM):
										self.countSMDs += 1

	def invoke(self, context, event):
		if self.properties.exportMode == 'NONE':
			ops.wm.call_menu(name="SMD_MT_ExportChoice")
			return {'PASS_THROUGH'}
		else: # a UI element has chosen a mode for us
			return self.execute(context)

	# nodes block
	def writeBones(self,quiet=False):
		smd = self.smd
		smd.file.write("nodes\n")

		if not smd.a:
			smd.file.write("0 \"root\" -1\nend\n")
			if not quiet: print("- No skeleton to export")
			return
		
		curID = 0
		if smd.a.data.smd_implicit_zero_bone:
			smd.file.write("0 \"blender_implicit\" -1\n")
			curID += 1
		
		# Write to file
		for bone in smd.a.data.bones:		
			if not bone.use_deform:
				print("- Skipping non-deforming bone \"{}\"".format(bone.name))
				continue

			parent = bone.parent
			while parent:
				if parent.use_deform:
					break
				parent = parent.parent

			line = "{} ".format(curID)
			smd.boneNameToID[bone.name] = curID
			curID += 1

			bone_name = bone.get('smd_name')
			if bone_name:
				comment = " # smd_name override from \"{}\"".format(bone.name)
			else:
				bone_name = bone.name
				comment = ""	
			line += "\"" + bone_name + "\" "

			if parent:
				line += str(smd.boneNameToID[parent.name])
			else:
				line += "-1"

			smd.file.write(line + comment + "\n")

		smd.file.write("end\n")
		num_bones = len(smd.a.data.bones)
		if not quiet: print("- Exported",num_bones,"bones")
		
		max_bones = 1023 if smd.isDMX else 128
		if num_bones > max_bones:
			self.warning("{} bone limit is {}, you have {}!".format("DMX" if smd.isDMX else "SMD",max_bones,num_bones))

	# skeleton block
	def writeFrames(self):
		smd = self.smd
		if smd.jobType == FLEX: # writeShapes() does its own skeleton block
			return

		smd.file.write("skeleton\n")

		if not smd.a:
			smd.file.write("time 0\n0 0 0 0 0 0 0\nend\n")
			return
		
		# remove any non-keyframed positions
		for posebone in smd.a.pose.bones:
			posebone.matrix_basis.identity()
		bpy.context.scene.update()

		# If this isn't an animation, mute all pose constraints
		if smd.jobType != ANIM:
			for bone in smd.a.pose.bones:
				for con in bone.constraints:
					con.mute = True

		# Get the working frame range
		num_frames = 1
		if smd.jobType == ANIM:
			action = smd.a.animation_data.action
			start_frame, last_frame = action.frame_range
			num_frames = int(last_frame - start_frame) + 1 # add 1 due to the way range() counts
			bpy.context.scene.frame_set(start_frame)
			
			if 'fps' in dir(action):
				bpy.context.scene.render.fps = action.fps
				bpy.context.scene.render.fps_base = 1

		# Start writing out the animation
		for i in range(num_frames):
			bpy.context.window_manager.progress_update(i / num_frames)
			smd.file.write("time {}\n".format(i))

			for posebone in smd.a.pose.bones:
				if not posebone.bone.use_deform: continue
		
				parent = posebone.parent	
				# Skip over any non-deforming parents
				while parent:
					if parent.bone.use_deform:
						break
					parent = parent.parent
		
				# Get the bone's Matrix from the current pose
				PoseMatrix = posebone.matrix
				if smd.a.data.smd_legacy_rotation:
					PoseMatrix *= mat_BlenderToSMD 
				if parent:
					if smd.a.data.smd_legacy_rotation: parentMat = parent.matrix * mat_BlenderToSMD 
					else: parentMat = parent.matrix
					PoseMatrix = parentMat.inverted() * PoseMatrix
				else:
					PoseMatrix = smd.a.matrix_world * PoseMatrix				
		
				# Get position
				pos = PoseMatrix.to_translation()
		
				# Apply armature scale
				if posebone.parent: # already applied to root bones
					scale = smd.a.matrix_world.to_scale()
					for j in range(3):
						pos[j] *= scale[j]
		
				# Get Rotation
				rot = PoseMatrix.to_euler()

				# Construct the string
				pos_str = rot_str = ""
				for j in [0,1,2]:
					pos_str += " " + getSmdFloat(pos[j])
					rot_str += " " + getSmdFloat(rot[j])
		
				# Write!
				smd.file.write( str(smd.boneNameToID[posebone.name]) + pos_str + rot_str + "\n" )

			# All bones processed, advance the frame
			bpy.context.scene.frame_set(bpy.context.scene.frame_current + 1)	

		smd.file.write("end\n")

		ops.object.mode_set(mode='OBJECT')
		
		print("- Exported {} frames{}".format(num_frames," (legacy rotation)" if smd.a.data.smd_legacy_rotation else ""))
		return
		
	def getWeightmap(self,ob):
		smd = self.smd
		out = []
		amod = smd.amod.get(ob['src_name'])
		if not amod: return out
		
		amod_vg = ob.vertex_groups.get(amod.vertex_group)
		
		num_verts = len(ob.data.vertices)
		for v in ob.data.vertices:
			weights = []
			total_weight = 0
			if len(out) % 50 == 0: bpy.context.window_manager.progress_update(len(out) / num_verts)
			
			if amod.use_vertex_groups:			
				for v_group in v.groups:
					if v_group.group < len(ob.vertex_groups):
						ob_group = ob.vertex_groups[v_group.group]
						group_name = ob_group.name
						group_weight = v_group.weight					
					else:
						continue # Vertex group might not exist on object if it's re-using a datablock				

					bone = amod.object.data.bones.get(group_name)
					if bone and bone.use_deform:
						weights.append([ smd.boneNameToID[bone.name], group_weight ])
						total_weight += group_weight			
					
			if amod.use_bone_envelopes and total_weight == 0: # vertex groups completely override envelopes
				for pose_bone in amod.object.pose.bones:
					if not pose_bone.bone.use_deform:
						continue
					weight = pose_bone.bone.envelope_weight * pose_bone.evaluate_envelope( ob.matrix_world * amod.object.matrix_world.inverted() * v.co )
					if weight:
						weights.append([ smd.boneNameToID[pose_bone.name], weight ])
						total_weight += weight
				
			# normalise weights, like Blender does. Otherwise Studiomdl puts anything left over onto the root bone.
			if total_weight not in [0,1]:
				for link in weights:
					link[1] *= 1/total_weight
			
			# apply armature modifier vertex group
			if amod_vg and total_weight > 0:
				amod_vg_weight = 0
				for v_group in v.groups:
					if v_group.group == amod_vg.index:
						amod_vg_weight = v_group.weight
						break
				if amod.invert_vertex_group:
					amod_vg_weight = 1 - amod_vg_weight
				for link in weights:
					link[1] *= amod_vg_weight

			out.append(weights)
		return out

	# triangles block
	def writePolys(self,internal=False):
		smd = self.smd
		if not internal:
			smd.file.write("triangles\n")
			have_cleared_pose = False

			if not bpy.context.scene.smd_use_image_names:
				materials = []
				for baked in smd.bakeInfo:
					if baked.type == 'MESH':
						for mat_slot in baked.material_slots:
							mat = mat_slot.material
							if mat and mat.get('smd_name') and mat not in materials:
								smd.file.write( "// Blender material \"{}\" has smd_name \"{}\"\n".format(mat.name,mat['smd_name']) )
								materials.append(mat)

			for baked in smd.bakeInfo:
				if baked.type == 'MESH':
					# write out each object in turn. Joining them would destroy unique armature modifier settings
					smd.m = baked
					if len(smd.m.data.polygons) == 0:
						self.error("Object {} has no faces, cannot export".format(smd.jobName))
						continue

					if smd.amod.get(smd.m['src_name']) and not have_cleared_pose:
						# This is needed due to a Blender bug. Setting the armature to Rest mode doesn't actually
						# change the pose bones' data!
						for posebone in smd.amod[smd.m['src_name']].object.pose.bones:
							posebone.matrix_basis.identity()
						bpy.context.scene.update()
						have_cleared_pose = True
					ops.object.mode_set(mode='OBJECT')

					self.writePolys(internal=True)

			smd.file.write("end\n")
			return

		# internal mode:

		md = smd.m.data
		face_index = 0

		uv_loop = md.uv_layers.active.data
		uv_tex = md.uv_textures.active.data
		
		weights = self.getWeightmap(smd.m)
		
		ob_weight_str = None
		if smd.m.get('bp'):
			ob_weight_str = " 1 {} 1".format(smd.boneNameToID[smd.m['bp']])
		elif len(weights) == 0:
			ob_weight_str = " 0"
		
		bad_face_mats = 0
		p = 0
		for poly in md.polygons:
			if p % 10 == 0: bpy.context.window_manager.progress_update(p / len(md.polygons))
			mat_name = None
			if not bpy.context.scene.smd_use_image_names and len(smd.m.material_slots) > poly.material_index:
				mat = smd.m.material_slots[poly.material_index].material
				if mat:
					mat_name = getObExportName(mat)
			if not mat_name and uv_tex:
				image = uv_tex[face_index].image
				if image:
					mat_name = os.path.basename(image.filepath) # not using data name as it can be truncated and custom props can't be used here
			if mat_name:
				smd.materials_used.add(mat_name)
			else:
				mat_name = "no_material"
				if smd.m.draw_type == 'TEXTURED':
					bad_face_mats += 1
			
			smd.file.write(mat_name + "\n")
			
			for i in range(len(poly.vertices)):
				# Vertex locations, normal directions
				loc = norms = ""
				v = md.vertices[poly.vertices[i]]
				norm = v.normal if poly.use_smooth else poly.normal
				for j in range(3):
					loc += " " + getSmdFloat(v.co[j])
					norms += " " + getSmdFloat(norm[j])

				# UVs
				uv = ""
				for j in range(2):
					uv += " " + getSmdFloat(uv_loop[poly.loop_start + i].uv[j])

				# Weightmaps
				weight_string = ""
				if ob_weight_str:
					weight_string = ob_weight_str
				else:
					valid_weights = 0
					for link in weights[v.index]:
						if link[1] > 0:
							weight_string += " {} {}".format(link[0], getSmdFloat(link[1]))
							valid_weights += 1
					weight_string = " {}{}".format(valid_weights,weight_string)

				# Finally, write it all to file
				smd.file.write("0" + loc + norms + uv + weight_string + "\n")

			face_index += 1

		if bad_face_mats:
			self.warning("{} faces on {} did not have a texture{} assigned".format(bad_face_mats,smd.jobName,"" if bpy.context.scene.smd_use_image_names else " or material"))
		print("- Exported",face_index,"polys")
		removeObject(smd.m)
		return

	# vertexanimation block
	def writeShapes(self):
		smd = self.smd
		num_verts = 0

		def _writeTime(time, shape = None):
			smd.file.write( "time {}{}\n".format(time, " # {}".format(shape['shape_name']) if shape else "") )

		# VTAs are always separate files. The nodes block is handled by the normal function, but skeleton is done here to afford a nice little hack
		smd.file.write("skeleton\n")
		
		for i in range(len(smd.bakeInfo)):
			shape = smd.bakeInfo[i]
			_writeTime(i, shape if i != 0 else None)
		smd.file.write("end\n")

		smd.file.write("vertexanimation\n")
		
		vert_offset = 0
		total_verts = 0
		smd.m = smd.bakeInfo[0]
		
		for i in range(len(smd.bakeInfo)):
			bpy.context.window_manager.progress_update((i+1) / (len(smd.bakeInfo)+1))
			_writeTime(i)
			shape = smd.bakeInfo[i]
			start_time = time.time()
			num_bad_verts = 0
			smd_vert_id = 0
			for poly in smd.m.data.polygons:
				for vert in poly.vertices:
					shape_vert = shape.data.vertices[vert]
					mesh_vert = smd.m.data.vertices[vert]
					if i != 0:
						diff_vec = shape_vert.co - mesh_vert.co
						for ordinate in diff_vec:
							if ordinate > 8:
								num_bad_verts += 1
								break
					if i == 0 or (diff_vec > epsilon or shape_vert.normal - mesh_vert.normal > epsilon):
						cos = norms = ""
						for x in range(3):
							cos += " " + getSmdFloat(shape_vert.co[x])
							norms += " " + getSmdFloat(shape_vert.normal[x])
						smd.file.write(str(smd_vert_id) + cos + norms + "\n")
						total_verts += 1
				
					smd_vert_id +=1
			if num_bad_verts:
				self.error("Shape \"{}\" has {} vertex movements that exceed eight units. Source does not support this!".format(shape['shape_name'],num_bad_verts))		
			if shape != smd.m:
				removeObject(shape)
		
		removeObject(smd.m)
		smd.file.write("end\n")
		print("- Exported {} flex shapes ({} verts)".format(i,total_verts))
		return

	# Creates a mesh with object transformations and modifiers applied
	def bakeObj(self,in_object):
		smd = self.smd
		if in_object.library:
			in_object = in_object.copy()
			bpy.context.scene.objects.link(in_object)
		if in_object.data and in_object.data.library:
			in_object.data = in_object.data.copy()
		
		bakes_in = []
		bakes_out = []
		for object in bpy.context.selected_objects:
			object.select = False
		bpy.context.scene.objects.active = in_object
		ops.object.mode_set(mode='OBJECT')
		
		def _ApplyVisualTransform(obj):
			if obj.data.users > 1:
				obj.data = obj.data.copy()
			
			top_parent = cur_parent = obj
			while(cur_parent):
				if not cur_parent.parent:
					top_parent = cur_parent
				cur_parent = cur_parent.parent
			
			if smd.jobType != ANIM:
				obj.matrix_world = getUpAxisMat(smd.upAxis).inverted() * obj.matrix_world

			bpy.context.scene.objects.active = obj
			ops.object.select_all(action='DESELECT')
			obj.select = True
			
			ops.object.parent_clear(type='CLEAR_KEEP_TRANSFORM')
			obj.location -= top_parent.location # undo location of topmost parent (potentially the object itself)
			ops.object.transform_apply(scale=True)
			if not smd.isDMX:
				ops.object.transform_apply(location=True,rotation=True)

		if in_object.type == 'ARMATURE':
			_ApplyVisualTransform(in_object)
			smd.a = in_object
		elif in_object.type in mesh_compatible:
			# hide all metaballs that we don't want
			for object in bpy.context.scene.objects:
				if (smd.g or object != in_object) and object.type == 'META' and (not object.smd_export or not (smd.g and smd.g in object.users_group)):
					for element in object.data.elements:
						element.hide = True
			bpy.context.scene.update() # actually found a use for this!!

			# get a list of objects we want to bake
			if not smd.g:
				bakes_in = [in_object]
			else:
				have_baked_metaballs = False
				validObs = getValidObs()
				flex_obs = []
				for object in smd.g.objects:
					if object.smd_export and object in validObs and not (object.type == 'META' and have_baked_metaballs):
						bakes_in.append(object)
						if not have_baked_metaballs: have_baked_metaballs = object.type == 'META'
						
				if smd.jobType == FLEX: # we can merge everything because we only care about the verts
					for ob in bpy.context.scene.objects:
						ob.select = ob in bakes_in
					bpy.context.scene.objects.active = bakes_in[0]
					ops.object.join()
					bakes_in = [bpy.context.scene.objects.active]
			
		# bake the list of objects!
		for i in range(len(bakes_in)):
			bpy.context.window_manager.progress_update(i / len(bakes_in))
			obj = bakes_in[i]
			solidify_fill_rim = False

			if obj.type in shape_types and obj.data.shape_keys:
				shape_keys = obj.data.shape_keys.key_blocks
			else:
				shape_keys = []

			if smd.jobType == FLEX or (smd.isDMX and len(shape_keys)):
				if obj.type not in shape_types:
					raise TypeError( "Shapes found on unsupported object type (\"{}\", {})".format(obj.name,obj.type) )				
				num_out = len(shape_keys)
			else:
				num_out = 1
			
			ops.object.mode_set(mode='OBJECT')
			ops.object.select_all(action="DESELECT")
			obj.select = True
			bpy.context.scene.objects.active = obj
			
			if obj.type == 'CURVE':
				obj.data.dimensions = '3D'

			if smd.jobType != FLEX: # we've already messed about with this object during ref export
				found_envelope = False
				
				# Bone parent
				if obj.parent_bone and obj.parent_type == 'BONE':
					smd.a = obj.parent
					obj['bp'] = obj.parent_bone
					found_envelope = True				
					
				# Bone constraint
				for con in obj.constraints:
					if con.mute:
						continue
					con.mute = True
					if con.type in ['CHILD_OF','COPY_TRANSFORMS'] and con.target.type == 'ARMATURE' and con.subtarget:
						if found_envelope:
							self.warning("Bone constraint \"{}\" found on \"{}\", which already has an envelope. Ignoring.".format(con.name,obj.name))
						else:
							smd.a = con.target
							obj['bp'] = con.subtarget
							found_envelope = True
				
				# Armature modifier
				for mod in obj.modifiers:
					if mod.type == 'ARMATURE' and mod.object:
						if found_envelope:
							self.warning("Armature modifier \"{}\" found on \"{}\", which already has an envelope. Ignoring.".format(mod.name,obj.name))
						else:
							smd.a = mod.object
							smd.amod[obj.name] = mod
							found_envelope = True
			
				if obj.type == "MESH":
					ops.object.mode_set(mode='EDIT')
					ops.mesh.reveal()
					ops.mesh.select_all(action="SELECT")
					if obj.matrix_world.is_negative:
						ops.mesh.flip_normals()
					ops.object.mode_set(mode='OBJECT')
				
				_ApplyVisualTransform(obj)
				
			# Apply modifiers; need to do this per shape key
			ops.object.mode_set(mode='OBJECT')
			for x in range(num_out):
				bpy.context.window_manager.progress_update((i + 1 + (x / num_out)) / (len(bakes_in) + 1))
				if shape_keys:
					cur_shape = shape_keys[x]
					obj.active_shape_key_index = x
					obj.show_only_shape_key = True
					if smd.jobType == FLEX and cur_shape.mute:
						self.warning("Skipping muted shape \"{}\"".format(cur_shape.name))
						continue
		
				if obj.type in mesh_compatible:
					has_edge_split = False
					for mod in obj.modifiers:
						if mod.type == 'EDGE_SPLIT':
							has_edge_split = True
						if mod.type == 'SOLIDIFY' and not solidify_fill_rim:
							solidify_fill_rim = mod.use_rim
						if smd.jobType == FLEX and mod.type == 'DECIMATE' and mod.decimate_type != 'UNSUBDIV':
							self.error("Cannot export shape keys from \"{}\" because it has a '{}' Decimate modifier. Only Un-Subdivide mode is supported.".format(obj.name,mod.decimate_type))
							return

					if not has_edge_split and obj.type == 'MESH':
						edgesplit = obj.modifiers.new(name="SMD Edge Split",type='EDGE_SPLIT') # creates sharp edges
						edgesplit.use_edge_angle = False
					
					data = obj.to_mesh(bpy.context.scene, True, 'PREVIEW') # bake it!
					baked = obj
					if obj.type == 'MESH':
						baked = baked.copy()
						baked.data = data
					else:
						baked = bpy.data.objects.new(obj.name, data)
					bpy.context.scene.objects.link(baked)
					bpy.context.scene.objects.active = baked
					baked.select = True
					baked['src_name'] = obj.name
					if smd.jobType == FLEX or (smd.isDMX and x > 0):
						baked.name = baked.data.name = baked['shape_name'] = cur_shape.name
					
					if smd.isDMX:
						if x == 0: bakes_out.append(baked)
						else: smd.dmxShapes[obj.name].append(baked)
						if smd.g:
							baked.smd_flex_controller_source = smd.g.smd_flex_controller_source
							baked.smd_flex_controller_mode = smd.g.smd_flex_controller_mode
					else:
						bakes_out.append(baked)
						ops.object.mode_set(mode='EDIT')
						ops.mesh.quads_convert_to_tris()
						ops.object.mode_set(mode='OBJECT')
						
					for mod in baked.modifiers:
						if mod.type == 'ARMATURE':
							mod.show_viewport = False
			
					# handle which sides of a curve should have polys
					if obj.type == 'CURVE':
						ops.object.mode_set(mode='EDIT')
						if obj.data.smd_faces == 'RIGHT':
							ops.mesh.duplicate()
							ops.mesh.flip_normals()
						if not obj.data.smd_faces == 'BOTH':
							ops.mesh.select_all(action='INVERT')
							ops.mesh.delete()
						elif solidify_fill_rim:
							self.warning("Curve {} has the Solidify modifier with rim fill, but is still exporting polys on both sides.".format(obj.name))
						ops.object.mode_set(mode='OBJECT')

					# project a UV map
					if smd.jobType != FLEX and len(baked.data.uv_textures) == 0:
						if len(baked.data.vertices) < 2000:
							ops.object.mode_set(mode='OBJECT')
							ops.object.select_all(action='DESELECT')
							baked.select = True
							ops.uv.smart_project()
						else:
							ops.object.mode_set(mode='EDIT')
							ops.mesh.select_all(action='SELECT')
							ops.uv.unwrap()
			
			ops.object.mode_set(mode='OBJECT')
			obj.select = False
		
		smd.bakeInfo.extend(bakes_out) # save to manager

	def writeSMD(self, object, groupIndex, filepath, smd_type = None, quiet = False ):
		smd = self.smd = SmdInfo()
		smd.jobType = smd_type
		smd.isDMX = filepath.endswith(".dmx")
		if groupIndex != -1:
			smd.g = object.users_group[groupIndex]
		smd.startTime = time.time()
		smd.uiTime = 0
		
		def _workStartNotice():
			if not quiet:
				print( "\nSMD EXPORTER: now working on {}{}".format(smd.jobName," (shape keys)" if smd.jobType == FLEX else "") )

		if object.type in mesh_compatible:
			# We don't want to bake any meshes with poses applied
			# NOTE: this won't change the posebone values, but it will remove deformations
			armatures = []
			for scene_object in bpy.context.scene.objects:
				if scene_object.type == 'ARMATURE' and scene_object.data.pose_position == 'POSE':
					scene_object.data.pose_position = 'REST'
					armatures.append(scene_object)

			if not smd.jobType:
				smd.jobType = REF
			if smd.g:
				smd.jobName = smd.g.name
			else:
				smd.jobName = getObExportName(object)
			smd.m = object
			_workStartNotice()
			#smd.a = smd.m.find_armature() # Blender bug: only works on meshes
			self.bakeObj(smd.m)
			if len(smd.bakeInfo) == 0:
				return False

			# re-enable poses
			for object in armatures:
				object.data.pose_position = 'POSE'
			bpy.context.scene.update()
		elif object.type == 'ARMATURE':
			if not smd.jobType:
				smd.jobType = ANIM
			smd.a = object
			smd.jobName = getObExportName(object.animation_data.action)
			_workStartNotice()
		else:
			raise TypeError("PROGRAMMER ERROR: writeSMD() has object not in",exportable_types)

		if smd.a and smd.jobType != FLEX:
			self.bakeObj(smd.a) # MUST be baked after the mesh		

		if smd.isDMX:
			return self.writeDMX(object, groupIndex, filepath, smd_type, quiet )
		
		try:
			smd.file = open(filepath, 'w')
		except Exception as err:
			self.error("Could not create SMD. Python reports: {}.".format(err))
		print("-",filepath)
			
		smd.file.write("version 1\n")

		# these write empty blocks if no armature is found. Required!
		self.writeBones(quiet = smd.jobType == FLEX)
		self.writeFrames()

		if smd.m:
			if smd.jobType in [REF,PHYS]:
				self.writePolys()
				print("- Exported {} materials".format(len(smd.materials_used)))
				for mat in smd.materials_used:
					print("   " + mat)
			elif smd.jobType == FLEX:
				self.writeShapes()

		smd.file.close()
		if not quiet: printTimeMessage(smd.startTime,smd.jobName,"export")

		return True

	def writeDMX(self, object, groupIndex, filepath, smd_type = None, quiet = False ):	
		smd = self.smd
		
		start = time.time()
		print("-",filepath)
		benchReset()
		
		if len(smd.bakeInfo) and smd.bakeInfo[0].smd_flex_controller_mode == 'ADVANCED' and not hasFlexControllerSource(smd.bakeInfo[0]):
			self.error( "Could not find flex controllers for \"{}\"".format(smd.jobName) )
			return
		
		def makeTransform(name,matrix,object_name):
			trfm = dm.add_element(name,"DmeTransform",id=object_name+"transform")
			trfm["position"] = datamodel.Vector3(matrix.to_translation())
			trfm["orientation"] = getDatamodelQuat(matrix.to_quaternion())
			return trfm
		
		dm = datamodel.DataModel("model",DatamodelFormatVersion())
		root = dm.add_element("root",id="Scene"+bpy.context.scene.name)
		DmeModel = dm.add_element(bpy.context.scene.name,"DmeModel",id="Object" + (smd.a.name if smd.a else smd.m.name))
		DmeModel["transform"] = makeTransform("upaxis",getUpAxisMat(smd.upAxis),"Scene"+bpy.context.scene.name)
		DmeModel_children = DmeModel["children"] = datamodel.make_array([],datamodel.Element)
		
		implicit_trfm = None
		
		if smd.jobType in [REF,ANIM]: # skeleton
			root["skeleton"] = DmeModel
			if DatamodelFormatVersion() >= 15:
				jointList = DmeModel["jointList"] = datamodel.make_array([],datamodel.Element)
			jointTransforms = DmeModel["jointTransforms"] = datamodel.make_array([],datamodel.Element)
			bone_transforms = {}
			
			def writeBone(bone):
				bone_name = bone.name if bone else "blender_implicit"
				
				bone_elem = dm.add_element(bone_name,"DmeJoint",id=bone_name)
				if DatamodelFormatVersion() >= 15: jointList.append(bone_elem)
				smd.boneNameToID[bone_name] = len(smd.boneNameToID)
				
				relMat = None
				if bone:
					if bone.parent: relMat = bone.parent.matrix.inverted() * bone.matrix
					else: relMat = smd.a.matrix_world * bone.matrix
				else:
					relMat = smd.a.matrix_world
				
				trfm = makeTransform(bone_name,relMat,"bone"+bone_name)
				
				# Apply armature scale
				scale = smd.a.matrix_world.to_scale()
				for j in range(3):
					trfm["position"][j] *= scale[j]
				
				jointTransforms.append(trfm)
				if bone:
					bone_transforms[bone] = trfm
				else:
					implicit_trfm = trfm
				bone_elem["transform"] = trfm
				
				if bone:
					children = bone_elem["children"] = datamodel.make_array([],datamodel.Element)
					for child in bone.children:
						children.append( writeBone(child) )
				
				bpy.context.window_manager.progress_update(len(jointTransforms)/num_bones)
				return bone_elem
		
			if smd.a:
				num_bones = len(smd.a.pose.bones)
				# remove any non-keyframed positions
				for posebone in smd.a.pose.bones:
					posebone.matrix_basis.identity()
				bpy.context.scene.update()
				
				if smd.a.data.smd_implicit_zero_bone:
					DmeModel_children.append(writeBone(None))
				
				for bone in smd.a.pose.bones:
					if not bone.parent:
						DmeModel_children.append(writeBone(bone))
						
			bench("skeleton")
			
		if smd.jobType == REF: # mesh
			root["model"] = DmeModel
			
			materials = {}
			dags = []
			for ob in smd.bakeInfo:
				ob_name = ob['src_name']
				src_ob = bpy.data.objects[ob_name]
				if ob.type != 'MESH': continue
				print("\n" + ob_name)
				vertex_data = dm.add_element("bind","DmeVertexData",id=ob_name+"verts")
				
				DmeMesh = dm.add_element(ob_name,"DmeMesh",id=ob_name)
				DmeMesh["visible"] = True			
				DmeMesh["bindState"] = vertex_data
				DmeMesh["currentState"] = vertex_data
				DmeMesh["baseStates"] = datamodel.make_array([vertex_data],datamodel.Element)
				
				trfm = makeTransform(ob_name, ob.matrix_world, "ob"+ob_name)
				jointTransforms.append(trfm)
				
				DmeDag = dm.add_element(ob_name,"DmeDag",id="ob"+ob_name+"dag")
				if DatamodelFormatVersion() >= 15: jointList.append(DmeDag)
				DmeDag["transform"] = trfm
				DmeDag["shape"] = DmeMesh
				dags.append(DmeDag)
				
				ob_weights = self.getWeightmap(ob)
				
				has_shapes = smd.dmxShapes.get(ob_name)
				
				jointCount = 0
				badJointCounts = 0
				if ob.get('bp'):
					jointCount = 1
				elif smd.amod.get(ob['src_name']):
					for vert_weights in ob_weights:
						count = len(vert_weights)
						if count > 3: badJointCounts += 1
						jointCount = max(jointCount,count)
					if smd.a.data.smd_implicit_zero_bone:
						jointCount += 1
						
				if badJointCounts:
					self.warning("{} verts on \"{}\" have over 3 weight links. Studiomdl does not support this!".format(badJointCounts,ob['src_name']))
				elif jointCount > 3: # due to implicit bone
					self.warning("Implicit motionless bone is pushing \"{}\" over the weight link limit.".format(ob['src_name']))
				
				format = [ "positions", "normals", "textureCoordinates" ]
				if jointCount: format.extend( [ "jointWeights", "jointIndices" ] )
				if has_shapes: format.append("balance")
				vertex_data["vertexFormat"] = datamodel.make_array( format, str)
				
				vertex_data["flipVCoordinates"] = True
				vertex_data["jointCount"] = jointCount
				
				pos = []
				norms = []
				texco = []
				texcoIndices = []
				jointWeights = []
				jointIndices = []
				balance = []
				
				Indices = []
				
				uv_layer = ob.data.uv_layers.active.data
				
				bench("setup")
				
				if ob.get('bp'):
					jointWeights = [ 1.0 ] * len(ob.data.vertices)
					jointIndices = [ smd.boneNameToID[ob['bp']] ] * len(ob.data.vertices)
				
				width = ob.dimensions.x * ( 1 - (src_ob.data.smd_flex_stereo_sharpness / 100) )
				num_verts = len(ob.data.vertices)
				for vert in ob.data.vertices:
					pos.append(datamodel.Vector3(vert.co))
					norms.append(datamodel.Vector3(vert.normal))
					vert.select = False
					
					if has_shapes:
						if width == 0:
							if vert.co.x == 0: balance_out = 0.5
							elif vert.co.x > 0: balance_out = 1
							else: balance_out = 0
						else:
							balance_out = (-vert.co.x / width / 2) + 0.5
							balance_out = min(1,max(0, balance_out))
						balance.append( float(balance_out) )
					
					if smd.a and not ob.get('bp'):
						weights = [0.0] * jointCount
						indices = [0] * jointCount
						i = 0
						total_weight = 0
						vert_weights = ob_weights[vert.index]
						for i in range(len(vert_weights)):
							indices[i] = vert_weights[i][0]
							weights[i] = vert_weights[i][1]
							total_weight += weights[i]
							i+=1
						if smd.a.data.smd_implicit_zero_bone and total_weight < 1:
							weights[-1] = float(1 - total_weight)
						
						jointWeights.extend(weights)
						jointIndices.extend(indices)
					if len(pos) % 50 == 0:
						bpy.context.window_manager.progress_update(len(pos) / num_verts)
					
				bench("verts")
				
				num_polys = len(ob.data.polygons)
				p = 0
				for poly in ob.data.polygons:
					i=0
					for vert_index in poly.vertices:
						vert = ob.data.vertices[vert_index]
						
						Indices.append(vert_index)
						
						uv = datamodel.Vector2(uv_layer[poly.loop_start + i].uv)					
						try:
							texcoIndices.append(texco.index(uv))
						except ValueError:
							texco.append(uv)
							texcoIndices.append(len(texco) - 1)
						
						i+=1
					p+=1
					if p % 10 == 0:
						bpy.context.window_manager.progress_update(p / num_polys)
				bench("polys")
				
				vertex_data["positions"] = datamodel.make_array(pos,datamodel.Vector3)
				vertex_data["positionsIndices"] = datamodel.make_array(Indices,int)
				
				vertex_data["normals"] = datamodel.make_array(norms,datamodel.Vector3)
				vertex_data["normalsIndices"] = datamodel.make_array(Indices,int)
				
				vertex_data["textureCoordinates"] = datamodel.make_array(texco,datamodel.Vector2)
				vertex_data["textureCoordinatesIndices"] = datamodel.make_array(texcoIndices,int)
				
				if jointCount:
					vertex_data["jointWeights"] = datamodel.make_array(jointWeights,float)
					vertex_data["jointIndices"] = datamodel.make_array(jointIndices,int)
				
				if has_shapes:
					vertex_data["balance"] = datamodel.make_array(balance,float)
					vertex_data["balanceIndices"] = datamodel.make_array(Indices,int)
				
				bench("insert")
				face_sets = {}
				bad_face_mats = 0
				vert_index = 0
				p = 0
				for poly in ob.data.polygons:
					mat_name = None
					if not bpy.context.scene.smd_use_image_names:
						try: mat_name = ob.material_slots[poly.material_index].material.name
						except: pass
					if not mat_name and smd.m.data.uv_textures.active:
						try: mat_name = os.path.basename(smd.m.data.uv_textures.active.data[poly.index].image.filepath)
						except: pass					
					if not mat_name:
						mat_name = "Material"
						bad_face_mats += 1
						
					if not face_sets.get(mat_name):
						material_elem = materials.get(mat_name)
						if not material_elem:
							materials[mat_name] = material_elem = dm.add_element(mat_name,"DmeMaterial",id=mat_name + "mat")
							mat_path = bpy.context.scene.smd_material_path.replace('\\','/')
							if (len(mat_path) > 0 and mat_path[-1] != '/'): mat_path += '/'
							material_elem["mtlName"] = mat_path + mat_name
						
						faceSet = dm.add_element(mat_name,"DmeFaceSet",id=ob_name+mat_name+"faces")
						faceSet["material"] = material_elem
						faceSet["faces"] = datamodel.make_array([],int)
						
						face_sets[mat_name] = faceSet
					
					face_list = face_sets[mat_name]["faces"]
					for vert in poly.vertices:
						face_list.append(vert_index)
						vert_index += 1
					face_list.append(-1)
					p+=1
					if p % 20 == 0:
						bpy.context.window_manager.progress_update(len(face_list) / num_polys)
				
				DmeMesh["faceSets"] = datamodel.make_array(list(face_sets.values()),datamodel.Element)
				if bad_face_mats:
					self.warning("{} faces on {} did not have a texture{} assigned".format(bad_face_mats,ob['src_name'],"" if bpy.context.scene.smd_use_image_names else " or material"))
				bench("faces")
				
				# shapes
				if has_shapes:
					shape_elems = []
					shape_names = []
					control_elems = []
					control_values = []
					delta_state_weights = []
					num_shapes = len(smd.dmxShapes[ob_name])
					for shape in smd.dmxShapes[ob_name]:
						shape_name = shape['shape_name']
						shape_names.append(shape_name)
						wrinkle_vg = ob.vertex_groups.get(shape_name)
						
						if src_ob.smd_flex_controller_mode == 'SIMPLE':
							DmeCombinationInputControl = dm.add_element(shape_name,"DmeCombinationInputControl",id=ob_name+shape_name+"controller")
							control_elems.append(DmeCombinationInputControl)
						
							DmeCombinationInputControl["rawControlNames"] = datamodel.make_array([shape_name],str)					
							if wrinkle_vg:
								DmeCombinationInputControl["wrinkleScales"] = datamodel.make_array([1.0],float)					
							control_values.append(datamodel.Vector3([0.5,0.5,0.5])) # ??
						
						delta_state_weights.append(datamodel.Vector2([0.0,0.0])) # ??
						
						DmeVertexDeltaData = dm.add_element(shape_name,"DmeVertexDeltaData",id=ob_name+shape_name)					
						shape_elems.append(DmeVertexDeltaData)
						
						vertexFormat = DmeVertexDeltaData["vertexFormat"] = datamodel.make_array([ "positions", "normals" ],str)
						
						wrinkle = []
						wrinkleIndices = []
						
						if wrinkle_vg: vertexFormat.append("wrinkle")
						
						# what do these do?
						#DmeVertexDeltaData["flipVCoordinates"] = False
						#DmeVertexDeltaData["corrected"] = True
						
						shape_pos = []
						shape_posIndices = []
						shape_norms = []
						shape_normIndices = []
						
						for i in range(len(ob.data.vertices)):
							ob_vert = ob.data.vertices[i]
							shape_vert = shape.data.vertices[i]
							
							if ob_vert.co != shape_vert.co:
								shape_pos.append(datamodel.Vector3(shape_vert.co - ob_vert.co))
								shape_posIndices.append(i)
								
							if ob_vert.normal != shape_vert.normal:
								shape_norms.append(datamodel.Vector3(shape_vert.normal))
								shape_normIndices.append(i)
							
							if wrinkle_vg:
								try:
									wrinkle.append(wrinkle_vg.weight(i))
									wrinkleIndices.append(i)
								except RuntimeError:
									pass
						
						DmeVertexDeltaData["positions"] = datamodel.make_array(shape_pos,datamodel.Vector3)
						DmeVertexDeltaData["positionsIndices"] = datamodel.make_array(shape_posIndices,int)
						DmeVertexDeltaData["normals"] = datamodel.make_array(shape_norms,datamodel.Vector3)
						DmeVertexDeltaData["normalsIndices"] = datamodel.make_array(shape_normIndices,int)
						if wrinkle_vg:
							DmeVertexDeltaData["wrinkle"] = datamodel.make_array(wrinkle,float)
							DmeVertexDeltaData["wrinkleIndices"] = datamodel.make_array(wrinkleIndices,int)
						
						removeObject(shape)
						bpy.context.window_manager.progress_update(len(shape_names) / num_shapes)
					DmeMesh["deltaStates"] = datamodel.make_array(shape_elems,datamodel.Element)
					DmeMesh["deltaStateWeights"] = datamodel.make_array(delta_state_weights,datamodel.Vector2)
					DmeMesh["deltaStateWeightsLagged"] = datamodel.make_array(delta_state_weights,datamodel.Vector2)
					
					first_pass = not root.get("combinationOperator")
					if ob.smd_flex_controller_mode == 'ADVANCED':
						if first_pass:
							text = bpy.data.texts.get(ob.smd_flex_controller_source)
							msg = "- Loading flex controllers from "
							element_path = [ "combinationOperator" ]
							if text:
								print(msg + "text block \"{}\"".format(text.name))
								controller_dm = datamodel.parse(text.as_string(),element_path=element_path)
							else:
								path = bpy.path.abspath(ob.smd_flex_controller_source)
								print(msg + path)
								controller_dm = datamodel.load(path=path,element_path=element_path)
						
							DmeCombinationOperator = controller_dm.root["combinationOperator"]
							root["combinationOperator"] = DmeCombinationOperator
						
						# replace target meshes
						targets = DmeCombinationOperator["targets"]
						added = False
						for elem in targets:
							if elem.type == "DmeFlexRules":
								if elem["deltaStates"][0].name in shape_names: # can't have the same delta name on multiple objects
									elem["target"] = DmeMesh
									added = True
							elif first_pass:
								targets.remove(elem)
						if not added:
							targets.append(DmeMesh)
					else:					
						if first_pass:
							DmeCombinationOperator = dm.add_element("combinationOperator","DmeCombinationOperator",id="controllers")
							DmeCombinationOperator["controls"] = datamodel.make_array([],datamodel.Element)
							DmeCombinationOperator["controlValues"] = datamodel.make_array([],datamodel.Vector3)
							DmeCombinationOperator["usesLaggedValues"] = False
							DmeCombinationOperator["targets"] = datamodel.make_array([],datamodel.Element)
							
							root["combinationOperator"] = DmeCombinationOperator
							
						DmeCombinationOperator["controls"].extend(control_elems)
						DmeCombinationOperator["controlValues"].extend(control_values)
						DmeCombinationOperator["targets"].append(DmeMesh)
					
					bench("shapes")			
			
				removeObject(ob)
			
			DmeModel_children.extend(dags)
		
		if smd.jobType == ANIM: # animation
			action = smd.a.animation_data.action
			
			if ('fps') in dir(action):
				fps = bpy.context.scene.render.fps = action.fps
				bpy.context.scene.render.fps_base = 1
			else:
				fps = bpy.context.scene.render.fps * bpy.context.scene.render.fps_base
			
			DmeChannelsClip = dm.add_element(action.name,"DmeChannelsClip",id=action.name+"clip")		
			DmeAnimationList = dm.add_element(smd.a.name,"DmeAnimationList",id=action.name+"list")
			DmeAnimationList["animations"] = datamodel.make_array([DmeChannelsClip],datamodel.Element)
			root["animationList"] = DmeAnimationList
			
			DmeTimeFrame = dm.add_element("timeframe","DmeTimeFrame",id=action.name+"time")
			duration = action.frame_range[1] / fps
			if DatamodelFormatVersion() >= 18:
				DmeTimeFrame["duration"] = datamodel.Time(duration)
			else:
				DmeTimeFrame["durationTime"] = int(duration * 10000)
			DmeTimeFrame["scale"] = 1.0
			DmeChannelsClip["timeFrame"] = DmeTimeFrame
			DmeChannelsClip["frameRate"] = int(fps)
			
			channels = DmeChannelsClip["channels"] = datamodel.make_array([],datamodel.Element)
			bone_channels = {}
			def makeChannel(bone):
				if bone: bone_channels[bone] = []
				channel_template = [
					[ "_p", "position", "Vector3", datamodel.Vector3 ],
					[ "_o", "orientation", "Quaternion", datamodel.Quaternion ]
				]
				name = bone.name if bone else "blender_implicit"
				for template in channel_template:
					cur = dm.add_element(name + template[0],"DmeChannel",id=name+template[0])
					cur["toAttribute"] = template[1]
					cur["toElement"] = bone_transforms[bone] if bone else jointTransforms[0]
					cur["mode"] = 1				
					val_arr = dm.add_element(template[2]+" log","Dme"+template[2]+"LogLayer",cur.name+"loglayer")				
					cur["log"] = dm.add_element(template[2]+" log","Dme"+template[2]+"Log",cur.name+"log")
					cur["log"]["layers"] = datamodel.make_array([val_arr],datamodel.Element)				
					val_arr["times"] = datamodel.make_array([],datamodel.Time if DatamodelFormatVersion() > 15 else int)
					val_arr["values"] = datamodel.make_array([],template[3])
					if bone: bone_channels[bone].append(val_arr)
					channels.append(cur)
			
			for bone in smd.a.pose.bones:
				makeChannel(bone)
			num_frames = int(action.frame_range[1] + 1)
			bench("Animation setup")
			prev_pos = {}
			prev_rot = {}
			
			for frame in range(0,num_frames):
				bpy.context.window_manager.progress_update(frame/num_frames)
				bpy.context.scene.frame_set(frame)
				keyframe_time = datamodel.Time(frame / fps) if DatamodelFormatVersion() > 15 else int(frame/fps * 10000)
				for bone in smd.a.pose.bones:
					if bone.parent: relMat = bone.parent.matrix.inverted() * bone.matrix
					else: relMat = smd.a.matrix_world * bone.matrix
					
					pos = relMat.to_translation()
					
					# Apply armature scale
					scale = smd.a.matrix_world.to_scale()
					for j in range(3):
						pos[j] *= scale[j]
					
					if not prev_pos.get(bone) or pos - prev_pos[bone] > epsilon:
						bone_channels[bone][0]["times"].append(keyframe_time)
						bone_channels[bone][0]["values"].append(datamodel.Vector3(pos))
					prev_pos[bone] = pos
					
					rot = relMat.to_quaternion()
					rot_vec = Vector(rot.to_euler())
					if not prev_rot.get(bone) or rot_vec - prev_rot[bone] > epsilon:
						bone_channels[bone][1]["times"].append(keyframe_time)
						bone_channels[bone][1]["values"].append(getDatamodelQuat(rot))
					prev_rot[bone] = rot_vec
					
				bench("frame {}".format(frame+1))
		
		benchReset()
		bpy.context.window_manager.progress_update(0.99)
		try:
			if bpy.context.scene.smd_use_kv2:
				dm.write(filepath,"keyvalues2",1)
			else:
				dm.write(filepath,"binary",DatamodelEncodingVersion())
		except (PermissionError, FileNotFoundError) as err:
			self.error("Could not create DMX. Python reports: {}.".format(err))
		bench("Writing")
		print("DMX export took",time.time() - start,"\n")
		
		return True
