#  The MIT License (MIT)
#  
#  Copyright (c) 2013 Tom Edwards contact@steamreview.org
#  
#  Permission is hereby granted, free of charge, to any person obtaining a copy
#  of this software and associated documentation files (the "Software"), to deal
#  in the Software without restriction, including without limitation the rights
#  to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
#  copies of the Software, and to permit persons to whom the Software is
#  furnished to do so, subject to the following conditions:
#  
#  The above copyright notice and this permission notice shall be included in
#  all copies or substantial portions of the Software.
#  
#  THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
#  IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
#  FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
#  AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
#  LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
#  OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
#  THE SOFTWARE.

import struct, array, io, binascii, collections
from struct import unpack,calcsize

header_format = "<!-- dmx encoding {:s} {:d} format {:s} {:d} -->"
header_format_regex = header_format.replace("{:d}","([0-9]+)").replace("{:s}","(\S+)")

header_proto2 = "<!-- DMXVersion binary_v{:d} -->"
header_proto2_regex = header_proto2.replace("{:d}","([0-9]+)")

intsize = calcsize("i")
shortsize = calcsize("H")
floatsize = calcsize("f")

def list_support():
	return { 'binary':[1,2,3,4,5], 'keyvalues2':[1],'binary_proto':[2] }

def check_support(encoding,encoding_ver):
	versions = list_support().get(encoding)
	if not versions:
		raise ValueError("DMX encoding \"{}\" is not supported".format(encoding))
	if encoding_ver not in versions:
		raise ValueError("Version {} of {} DMX is not supported".format(encoding_ver,encoding))

def _encode_binary_string(string):
	return bytes(string,'ASCII') + bytes(1)

_kv2_indent = 0
def _get_kv2_indent():
	return '\t' * _kv2_indent

def _validate_array_list(l,array_type):
	if not l: return
	try:
		for i in range(len(l)):
			if type(l[i]) != array_type:
				l[i] = array_type(l[i])
	except:
		raise TypeError("Could not convert all values to {}".format(array_type))
			
def _quote(str):
	return "\"{}\"".format(str)
	
def get_bool(file):
	return file.read(1) != b'\x00'
def get_byte(file):
	return int(unpack("B",file.read(1))[0])
def get_char(file):
	c = file.read(1)
	if type(c) == str: return c
	return unpack("c",c)[0].decode('ASCII')
def get_int(file):
	return int( unpack("i",file.read(intsize))[0] )
def get_short(file):
	return int( unpack("H",file.read(shortsize))[0] )
def get_float(file):
	return float( unpack("f",file.read(floatsize))[0] )
def get_vec(file,dim):
	return list( unpack("{}f".format(dim),file.read(floatsize*dim)) )
def get_color(file):
	return Color(list(unpack("4B",file.read(4))))
	
def get_str(file):
	out = ""
	while True:
		cur = file.read(1)
		if cur == b'\x00': return out
		out += cur.decode('ASCII')

def _get_kv2_repr(var):
	t = type(var)
	if t == bool:
		return "1" if var else "0"
	elif t == float:
		out = "{:.10f}".format(var)
		return out.rstrip("0").rstrip(".") # two-step to protect 10.0000 etc.
	elif t == Element:
		return str(var.id)
	elif issubclass(t, _Array):
		return var.to_kv2()
	elif t == Binary:
		return binascii.hexlify(var).decode('ASCII')
	elif var == None:
		return ""
	else:
		return str(var)

class _Array(list):
	type = None
	type_str = ""	
	
	def __init__(self,l=None):
		_validate_array_list(l,self.type)
		if l:
			return super().__init__(l)
		else:
			return super().__init__()
		
	def to_kv2(self):
		if len(self) == 0:
			return "[ ]"
		if self.type == Element:
			out = "\n{}[\n".format(_get_kv2_indent())
			global _kv2_indent
			_kv2_indent += 1
		else:
			out = "[ "
		
		for i,item in enumerate(self):
			if i > 0: out += ", "
			if self.type == Element:				
				if i > 0: out += "\n"
				if item._users == 1:
					out += _get_kv2_indent() + item.get_kv2()
				else:
					out += "{}{} {}".format(_get_kv2_indent(),_quote("element"),_quote(item.id))				
			else:
				out += _quote(_get_kv2_repr(item))
		
		if self.type == Element:
			_kv2_indent -= 1
			return "{}\n{}]".format(out,_get_kv2_indent())
		else:
			return "{} ]".format(out)
		
	def frombytes(self,file):
		length = get_int(file)		
		self.extend( unpack( typestr*length, file.read( calcsize(typestr) * length) ) )

class _BoolArray(_Array):
	type = bool
	type_str = "b"
class _IntArray(_Array):
	type = int
	type_str = "i"
class _FloatArray(_Array):
	type = float
	type_str = "f"
class _StrArray(_Array):
	type = str

class _Vector(list):
	type_str = ""
	def __init__(self,list):
		_validate_array_list(list,float)
		if len(list) != len(self.type_str):
			raise TypeError("Expected {} values".format(len(self.type_str)))
		super().__init__(list)
		
	def __repr__(self):
		out = ""
		for i,ord in enumerate(self):
			if i > 0: out += " "
			out += _get_kv2_repr(ord)
			
		return out
	
	def tobytes(self):
		out = bytes()
		for ord in self: out += struct.pack("f",ord)
		return out
		
class Vector2(_Vector):
	type_str = "ff"
class Vector3(_Vector):
	type_str = "fff"
class Vector4(_Vector):
	type_str = "ffff"
class Quaternion(Vector4):
	'''XYZW'''
	pass
class Angle(Vector3):
	pass
class _VectorArray(_Array):
	type = list
	def __init__(self,list=None):
		_validate_array_list(self,list)
		_Array.__init__(self,list)
class _Vector2Array(_VectorArray):
	type = Vector2
class _Vector3Array(_VectorArray):
	type = Vector3
class _Vector4Array(_VectorArray):
	type = Vector4
class _QuaternionArray(_Vector4Array):
	type = Quaternion
class _AngleArray(_Vector3Array):
	type = Angle

class Matrix(list):
	type = list
	def __init__(self,matrix=None):
		if matrix:
			attr_error = AttributeError("Matrix must contain 4 lists of 4 floats")
			if len(matrix) != 4: raise attr_error
			for row in matrix:
				if len(row) != 4: raise attr_error
				for item in row:
					if type(item) != float: raise attr_error
			
		super().__init__(matrix)
	def tobytes(self,datamodel,elem):
		out = bytes()
		for row in self: # or is it column first? Doesn't matter here, so whatever.
			for item in row:
				out += item.tobytes()
		return out
	
class _MatrixArray():
	type = Matrix

class Binary(bytes):
	pass
class _BinaryArray(_Array):
	type = Binary
	type_str = "b"

class Color(Vector4):
	type = int
	type_str = "iiii"
	def tobytes(self):
		out = bytes()
		for i in self:
			out += bytes(int(self[i]))
		return out
class _ColorArray(_Vector4Array):
	pass
	
class Time(float):
	@classmethod
	def from_int(self,int_value):
		return Time(int_value / 10000)
		
	def tobytes(self):
		return struct.pack("i",int(self * 10000))

class _TimeArray(_Array):
	type = Time
		
def make_array(list,t):
	if t not in _dmxtypes_all:
		raise TypeError("{} is not a valid datamodel attribute type".format(t))
	return _get_array_type(t)(list)
		
class AttributeError(KeyError):
	'''Raised when an attribute is not found on an element. Essentially a KeyError, but subclassed because it's normally an unrecoverable data issue.'''
	pass

class IDCollisionError(Exception):
	pass

_array_types = [list,set,tuple,array.array]
class Element(collections.OrderedDict):
	'''Effectively a dictionary, but keys must be str. Also contains a name (str), type (str) and ID (uuid.UUID, can be generated from str).'''
	_datamodels = None
	_users = 0
	
	def __init__(self,datamodel,name,elemtype="DmElement",id=None,_is_placeholder=False):
		# Blender bug: importing uuid causes a runtime exception. The return value is not affected, thankfully.
		# http://projects.blender.org/tracker/index.php?func=detail&aid=28732&group_id=9&atid=498
		import uuid
		
		if type(name) != str:
			raise TypeError("name must be a string")
		
		if elemtype and type(elemtype) != str:
			raise TypeError("elemtype must be a string")
		
		if id and type(id) not in [uuid.UUID, str]:
			raise TypeError("id must be a UUID or a string")
			
		self.name = name
		self.type = elemtype
		self._is_placeholder = _is_placeholder
		self._datamodels = set()
		self._datamodels.add(datamodel)
		
		if id:
			if type(id) == uuid.UUID:
				self.id = id
			else:
				self.id = uuid.uuid3(uuid.UUID('20ba94f8-59f0-4579-9e01-50aac4567d3b'),str(id))
		else:
			self.id = uuid.uuid4()
		
		super().__init__()
		
	def __eq__(self,other):
		return other and self.id == other.id

	def __repr__(self):
		return "<Datamodel element \"{}\" ({})>".format(self.name,self.type)
		
	def __hash__(self):
		return int(self.id)
		
	def __getitem__(self,item):
		if type(item) != str: raise TypeError("Attribute name must be a string, not {}".format(type(item)))
		try:
			return super().__getitem__(item)
		except KeyError:
			raise AttributeError("No attribute \"{}\" on {}".format(item,self))
			
	def __setitem__(self,key,item):
		if type(key) != str: raise TypeError("Attribute name must be string, not {}".format(type(key)))
		
		def import_element(elem):
			for dm in self._datamodels:
				if dm in elem._datamodels: continue
				for dm_e in dm.elements:
					if dm_e.id == elem.id:
						raise IDCollisionError("Could not add {} to {}: element ID collision with {}.".format(elem, dm, dm_e))
				dm.elements.append(elem)
				elem._datamodels.add(dm)
				for attr in elem.values():
					t = type(attr)
					if t == Element:
						import_element(attr)
					if t == _ElementArray:
						for arr_elem in attr:
							import_element(arr_elem)
		
		t = type(item)
		
		if t in _dmxtypes_all or t == type(None):
			if t == Element:
					import_element(item)
			elif t == _ElementArray:
				for arr_elem in item:
					import_element(arr_elem)
			
			return super().__setitem__(key,item)
		else:
			if t in _array_types:
				raise ValueError("Cannot create an attribute from a generic Python list. Use make_array() first.")
			else:
				raise ValueError("Invalid attribute type ({})".format(t))
		
	def get_kv2(self,deep = True):
		out = ""
		out += _quote(self.type)
		out += "\n" + _get_kv2_indent() + "{\n"
		global _kv2_indent
		_kv2_indent += 1
		
		def _make_attr_str(attr, is_array = False):
			attr_str = _get_kv2_indent()
			
			for i,item in enumerate(attr):
				if i > 0: attr_str += " "
				
				if is_array and i == 2:
					attr_str += str(item)
				else:
					attr_str += _quote(item)
			
			return attr_str + "\n"
		
		out += _make_attr_str([ "id", "elementid", self.id ])
		out += _make_attr_str([ "name", "string", self.name ])
		
		for name in self:
			attr = self[name]
			if attr == None:
				out += _make_attr_str([ name, "element", "" ])
				continue
			
			t = type(attr)
			
			if t == Element and attr._users < 2 and deep:
				out += _get_kv2_indent()
				out += _quote(name)
				out += " {}".format( attr.get_kv2() )
				out += "\n"
			else:				
				if issubclass(t,_Array):
					if t == _ElementArray:
						type_str = "element_array"
					else:
						type_str = _dmxtypes_str[_dmxtypes_array.index(t)] + "_array"
				else:
					type_str = _dmxtypes_str[_dmxtypes.index(t)]
				
				out += _make_attr_str( [
					name,
					type_str,
					_get_kv2_repr(attr)
				], issubclass(t,_Array) )
		_kv2_indent -= 1
		out += _get_kv2_indent() + "}"
		return out

class _ElementArray(_Array):
	type = Element

_dmxtypes = [Element,int,float,bool,str,Binary,Time,Color,Vector2,Vector3,Vector4,Angle,Quaternion,Matrix]
_dmxtypes_array = [_ElementArray,_IntArray,_FloatArray,_BoolArray,_StrArray,_BinaryArray,_TimeArray,_ColorArray,_Vector2Array,_Vector3Array,_Vector4Array,_AngleArray,_QuaternionArray,_MatrixArray]
_dmxtypes_all = _dmxtypes + _dmxtypes_array
_dmxtypes_str = ["element","int","float","bool","string","binary","time","color","vector2","vector3","vector4","angle","quaternion","matrix"]

attr_list_v1 = [
	None,Element,int,float,bool,str,Binary,"ObjectID",Color,Vector2,Vector3,Vector4,Angle,Quaternion,Matrix,
	_ElementArray,_IntArray,_FloatArray,_BoolArray,_StrArray,_BinaryArray,"_ObjectIDArray",_ColorArray,_Vector2Array,_Vector3Array,_Vector4Array,_AngleArray,_QuaternionArray,_MatrixArray
] # ObjectID is an element UUID
attr_list_v2 = [
	None,Element,int,float,bool,str,Binary,Time,Color,Vector2,Vector3,Vector4,Angle,Quaternion,Matrix,
	_ElementArray,_IntArray,_FloatArray,_BoolArray,_StrArray,_BinaryArray,_TimeArray,_ColorArray,_Vector2Array,_Vector3Array,_Vector4Array,_AngleArray,_QuaternionArray,_MatrixArray
]

def _get_type_from_string(type_str):
	return _dmxtypes[_dmxtypes_str.index(type_str)]
def _get_array_type(single_type):
	if single_type in _dmxtypes_array: raise ValueError("Argument is already an array type")
	return _dmxtypes_array[ _dmxtypes.index(single_type) ]
def _get_single_type(array_type):
	if array_type in _dmxtypes: raise ValueError("Argument is already a single type")
	return _dmxtypes[ _dmxtypes_array.index(array_type) ]

def _get_dmx_id_type(encoding,version,id):	
	if encoding in ["binary","binary_proto"]:
		if version in [1,2]:
			return attr_list_v1[id]
		if version in [3,4,5]:
			return attr_list_v2[id]
	if encoding == "keyvalues2":
		return _dmxtypes[ _dmxtypes_str.index(id) ]
				
	raise ValueError("Type ID {} invalid in {} {}".format(id,encoding,version))
	
def _get_dmx_type_id(encoding,version,t):	
	if t == type(None): t = Element
	if encoding == "keyvalues2": raise ValueError("Type IDs do not exist in KeyValues2")
	try:
		if encoding == "binary":
			if version in [1,2]:
				return attr_list_v1.index(t)
			if version in [3,4,5]:
				return attr_list_v2.index(t)
		elif encoding == "binary_proto":
			return attr_list_v1.index(t)
	except:
		raise ValueError("Type {} not supported in {} {}".format(t,encoding,version))

class _StringDictionary(list):
	dummy = False
	
	def __init__(self,encoding,encoding_ver,in_file=None,out_datamodel=None):
		if encoding == "binary":
			self.indice_size = self.length_size = intsize
				
			if encoding_ver == 4:
				self.indice_size = shortsize
			elif encoding_ver in [3,2]:
				self.indice_size = self.length_size = shortsize
			elif encoding_ver == 1:
				self.dummy = True
				return
		elif encoding == "binary_proto":
			self.dummy = True
			return
		
		if in_file:
			num_strings = get_short(in_file) if self.length_size == shortsize else get_int(in_file)
			for i in range(num_strings):
				self.append(get_str(in_file))
		
		elif out_datamodel:
			checked = []
			string_set = set()
			def process_element(elem):
				checked.append(elem)
				string_set.add(elem.name)
				string_set.add(elem.type)
				for name in elem:
					attr = elem[name]
					string_set.add(name)
					if type(attr) == str: string_set.add(attr)
					elif type(attr) == Element:
						if attr not in checked: process_element(attr)
					elif type(attr) == _ElementArray:
						for i in attr:
							if i not in checked: process_element(i)
			process_element(out_datamodel.root)
			self.extend(string_set)
		
	def read_string(self,in_file):
		if self.dummy:
			return get_str(in_file)
		else:
			return self[get_short(in_file) if self.indice_size  == shortsize else get_int(in_file)]
			
	def write_string(self,out_file,string):
		if self.dummy:
			out_file.write( _encode_binary_string(string) )
		else:
			assert(string in self)
			out_file.write( struct.pack("H" if self.indice_size == shortsize else "i", self.index(string) ) )
		
	def write_dictionary(self,out_file):
		if not self.dummy:
			out_file.write( struct.pack("H" if self.length_size == shortsize else "i", len(self) ) )
			for string in self:
				out_file.write( _encode_binary_string(string) )
	
class DataModel:
	'''Container for Element objects. Has a format name (str) and format version (int). Can write itself to a string object or a file.'''
	elements = None
	root = None
	
	def __init__(self,format,format_ver):
		if (format and type(format) != str) or (format_ver and type(format_ver) != int):
			raise TypeError("Expected str, int")
		
		self.format = format
		self.format_ver = format_ver
		
		self.elements = []
		
	def __repr__(self):
		return "<Datamodel 0x{}{}>".format(id(self)," (root is \"{}\")".format(self.root.name) if self.root else "")
		
	def add_element(self,name,elemtype="DmElement",id=None,_is_placeholder=False):
		elem = Element(self,name,elemtype,id,_is_placeholder)
		try:
			dupe_elem = self.elements.index(elem)
			if not self.elements[dupe_elem]._is_placeholder: raise ValueError("ID {} already in use in this datamodel.".format(id))
		except: pass
		self.elements.append(elem)
		elem.datamodel = self
		if len(self.elements) == 1: self.root = elem
		return elem
		
	def find_elements(self,name=None,id=None,elemtype=None):
		out = []
		import uuid
		if type(id) == str: id = uuid.UUID(id)
		for elem in self.elements:
			if elem.id == id: return elem
			if elem.name == name: out.append(elem)
			if elem.type == elemtype: out.append(elem)
		if len(out): return out
		
	def _write(self,value, elem = None, suppress_dict = False):
		import uuid
		t = type(value)
		
		if t in [bytes,Binary]:
			if t == Binary:
				self.out.write( struct.pack("i",len(value)) )
			self.out.write(value)
		
		elif t == uuid.UUID:
			self.out.write(value.bytes)
		elif t == Element:
			if value._is_placeholder:
				if self.encoding_ver < 5:
					self._write(-1)
				else:
					self._write(-2)
					self._write(str(value.id))
			else:
				self._write(self.elem_chain.index(value),elem)
		elif t == str:
			if suppress_dict:
				self.out.write( _encode_binary_string(value) )
			else:
				self._string_dict.write_string(self.out,value)
				
		elif issubclass(t, _Array):
			self.out.write( struct.pack("i",len(value)) )
			for item in value:
				self._write(item,suppress_dict=True)
		elif issubclass(t,_Vector) or t == Time:
			self.out.write(value.tobytes())
		
		elif t == bool:
			self.out.write( struct.pack("b",value) )
		elif t == int:
			self.out.write( struct.pack("i",value) )
		elif t == float:
			self.out.write( struct.pack("f",value) )
			
		else:
			raise TypeError("Cannot write attributes of type {}".format(t))
	
	def _write_element_index(self,elem):
		if elem._is_placeholder: return
		self._write(elem.type)
		self._write(elem.name, suppress_dict = self.encoding_ver < 4)
		self._write(elem.id)
		
		self.elem_chain.append(elem)
		
		for name in elem:
			attr = elem[name]
			t = type(attr)
			if t == Element and attr not in self.elem_chain:
				self._write_element_index(attr)
			if t == _ElementArray:
				for i in attr:
					if i not in self.elem_chain:
						self._write_element_index(i)
		
	def _write_element_props(self):	
		for elem in self.elem_chain:
			if elem._is_placeholder: continue
			self._write(len(elem))
			for name in elem:
				attr = elem[name]
				self._write(name)
				self._write( struct.pack("b", _get_dmx_type_id(self.encoding, self.encoding_ver, type(attr) )) )
				if attr == None:
					self._write(-1)
				else:
					self._write(attr,elem, suppress_dict = self.encoding_ver < 4)
					
	def echo(self,encoding,encoding_ver):
		check_support(encoding, encoding_ver)
		
		if encoding in ["binary", "binary_proto"]:
			self.out = io.BytesIO()
		else:
			self.out = io.StringIO()
			global _kv2_indent
			_kv2_indent = 0
		
		self.encoding = encoding
		self.encoding_ver = encoding_ver
		
		if self.encoding == 'binary_proto':
			self.out.write( _encode_binary_string(header_proto2.format(encoding_ver) + "\n") )
		else:
			header = header_format.format(encoding,encoding_ver,self.format,self.format_ver)
			if self.encoding == 'binary':
				self.out.write( _encode_binary_string(header + "\n") )
			elif self.encoding == 'keyvalues2':
				self.out.write(header + "\n")
		
		if encoding == 'binary':
			self._string_dict = _StringDictionary(encoding,encoding_ver,out_datamodel=self)
			self._string_dict.write_dictionary(self.out)
			
		# count elements
		out_elems = []
		for elem in self.elements:
			elem._users = 0
		def _count_child_elems(elem):
			out_elems.append(elem)
			for name in elem:
				attr = elem[name]
				t = type(attr)
				if t == Element:
					if attr not in out_elems:
						_count_child_elems(attr)
					attr._users += 1
				elif t == _ElementArray:
					for i in attr:
						if i not in out_elems:
							_count_child_elems(i)
						i._users += 1
		_count_child_elems(self.root)
		
		if self.encoding in ["binary", "binary_proto"]:
			self._write(len(out_elems))
			self.elem_chain = []
			self._write_element_index(self.root)
			self._write_element_props()
		elif self.encoding == 'keyvalues2':
			self.out.write(self.root.get_kv2() + "\n\n")
			for elem in out_elems:
				if elem._users > 1:
					self.out.write(elem.get_kv2() + "\n\n")
				
		self._string_dict = None
		return self.out.getvalue()
		
	def write(self,path,encoding,encoding_ver):
		with open(path,'wb' if encoding in ["binary","binary_proto"] else 'w') as file:
			file.write(self.echo(encoding,encoding_ver))

def parse(parse_string, element_path=None):
	return load(in_file=io.StringIO(parse_string),element_path=element_path)

def load(path = None, in_file = None, element_path = None):
	if bool(path) == bool(in_file):
		raise ValueError("A path string OR a file object must be provided")
	if element_path != None and type(element_path) != list:
		raise TypeError("element_path must be a list containing element names")
	if not in_file:
		in_file = open(path,'rb')
	
	try:
		import re, uuid
		
		try:
			header = ""
			while True:
				header += get_char(in_file)
				if header.endswith(">"): break
			
			matches = re.findall(header_format_regex,header)
			
			if len(matches) != 1 or len(matches[0]) != 4:
				matches = re.findall(header_proto2_regex,header)
				if len(matches) == 1 and len(matches[0]) == 1:
					encoding = "binary_proto"
					encoding_ver = int(matches[0][0])
					format = "undefined_format"
					format_ver = 0
				else:
					raise Exception()
			else:
				encoding,encoding_ver, format,format_ver = matches[0]
				encoding_ver = int(encoding_ver)
				format_ver = int(format_ver)
		except:
			raise Exception("Could not read DMX header")
		
		check_support(encoding,encoding_ver)
		dm = DataModel(format,format_ver)
		
		max_elem_path = len(element_path) + 1 if element_path else 0
		
		if encoding == 'keyvalues2':
			class AttributeReference:
				def __init__(self,Owner,Name,Index=-1):
					self.Owner = Owner
					self.Name = Name
					self.Index = Index
			
			def parse_line(line):
				return re.findall("\"(.*?)\"",line.strip("\n\t ") )
				
			def read_element(elem_type):
				id = None
				name = None
				
				def read_value(name,type_str,kv2_value, index=-1):
					if type_str == 'element': # make a record; will link everything up once all elements have been read
						if not kv2_value:
							return None
						else:
							element_users[kv2_value].append(AttributeReference(element_chain[-1], name, index))
							return dm.add_element("Missing element",id=uuid.UUID(hex=kv2_value),_is_placeholder=True)
					
					elif type_str == 'string': return kv2_value
					elif type_str == 'int': return int(kv2_value)
					elif type_str == 'float': return float(kv2_value)
					elif type_str == 'bool': return bool(int(kv2_value))
					elif type_str == 'time': return Time(kv2_value)
					elif type_str.startswith('vector') or type_str in ['color','quaternion','angle']:
						return _get_type_from_string(type_str)( [float(i) for i in kv2_value.split(" ")] )
				
				new_elem = None
				for line_raw in in_file:
					if line_raw.strip("\n\t, ").endswith("}"):
						#print("{}- {}".format('\t' * (len(element_chain)-1),element_chain[-1].name))
						return element_chain.pop()
					
					line = parse_line(line_raw)
					if len(line) == 0:
						continue
					
					if line[0] == 'id': id = uuid.UUID(hex=line[2])
					elif line[0] == 'name': name = line[2]
					
					# don't read elements outside the element path
					if max_elem_path and name and len(dm.elements):
						if len(element_path):
							skip = name.lower() != element_path[0].lower()
						else:
							skip = len(element_chain) < max_elem_path
						if skip:
							child_level = 0
							for line_raw in in_file:
								if "{" in line_raw: child_level += 1
								if "}" in line_raw:
									if child_level == 0: return
									else: child_level -= 1
							return
						elif len(element_path):
							del element_path[0]
					
					if id and name:
						new_elem = dm.add_element(name,elem_type,id)
						element_chain.append(new_elem)
						#print("{}+ {}".format('\t' * (len(element_chain)-1),element_chain[-1].name))
						id = name = None
						continue
					
					if new_elem == None:
						continue
					
					if len(line) >= 2:
						if line[1] == "element_array":
							arr_name = line[0]
							arr = _ElementArray()
							
							if "[" not in line_raw: # immediate "[" means and empty array; elements must be on separate lines
								for line in in_file:
									if "[" in line: continue
									if "]" in line: break
									line = parse_line(line)
									
									if len(line) == 1:
										arr.append( read_element(line[0]) )
									elif len(line) == 2:
										arr.append( read_value(arr_name,"element",line[1],index=len(arr)) )								
							
							element_chain[-1][arr_name] = arr
							continue
						
						elif line[1].endswith("_array"):
							arr_name = line[0]
							arr_type_str = line[1].split("_")[0]
							arr = _get_array_type(_get_type_from_string(arr_type_str))()
							
							if "[" in line_raw: # one-line array
								for item in line[2:]:
									arr.append(read_value(arr_name,arr_type_str,item))
								element_chain[-1][arr_name] = arr
								
							else: # multi-line array
								for line in in_file:
									if "[" in line:
										continue
									if "]" in line:
										element_chain[-1][arr_name] = arr
										break
										
									line = parse_line(line)
									arr.append(read_value(arr_name,arr_type_str,line[0]))
						
						elif len(line) == 2: # inline element
							element_chain[-1][line[0]] = read_element(line[1])
						elif len(line) == 3: # ordinary attribute or element ID
							element_chain[-1][line[0]] = read_value(line[0],line[1],line[2])

				raise IOError("Unexpected EOF")
			
			if ('mode' in dir(in_file) and 'b' in in_file.mode): in_file = io.TextIOWrapper(in_file)
			in_file.seek(len(header))
			
			element_chain = []
			element_users = collections.defaultdict(list)
			for line in in_file:
				line = parse_line(line)
				if len(line) == 0: continue
				
				if len(element_chain) == 0 and len(line) == 1:
					read_element(line[0])
			
			for element in dm.elements:
				if element._is_placeholder == True: continue
				users = element_users[str(element.id)]
				for user_info in users:
					if user_info.Index == -1:
						user_info.Owner[user_info.Name] = element
					else:
						user_info.Owner[user_info.Name][user_info.Index] = element
				
		elif encoding in ['binary', 'binary_proto']:
			in_file.seek(2,1) # skip header's line break and null terminator
			
			dm._string_dict = _StringDictionary(encoding,encoding_ver,in_file=in_file)
			
			num_elements = get_int(in_file)
			
			# element headers
			for i in range(num_elements):
				elemtype = dm._string_dict.read_string(in_file)
				name = dm._string_dict.read_string(in_file) if encoding_ver >= 4 else get_str(in_file)
				id = uuid.UUID(bytes_le = in_file.read(16)) # little-endian
				dm.add_element(name,elemtype,id)
			
			# attributes
			def get_value(attr_type,from_array = False):
				if attr_type == Element:
					element_index = get_int(in_file)
					if element_index == -1:
						return None
					elif element_index == -2:
						return dm.add_element("Missing element",id=uuid.UUID(hex=get_str(in_file)),_is_placeholder=True)
					else:
						return dm.elements[element_index]
					
				elif attr_type == str:		return get_str(in_file) if encoding_ver < 4 or from_array else dm._string_dict.read_string(in_file)
				elif attr_type == int:		return get_int(in_file)
				elif attr_type == float:	return get_float(in_file)
				elif attr_type == bool:		return get_bool(in_file)
					
				elif attr_type == Vector2:		return Vector2(get_vec(in_file,2))
				elif attr_type == Vector3:		return Vector3(get_vec(in_file,3))
				elif attr_type == Angle:		return Angle(get_vec(in_file,3))
				elif attr_type == Vector4:		return Vector4(get_vec(in_file,4))
				elif attr_type == Quaternion:	return Quaternion(get_vec(in_file,4))
				elif attr_type == Matrix:
					out = []
					for i in range(4): out.append(get_vec(in_file,4))
					return Matrix(out)
					
				elif attr_type == Color:		return get_color(in_file)
				elif attr_type == Time: return Time.from_int(get_int(in_file))
				elif attr_type == Binary: return Binary(in_file.read(get_int(in_file)))
					
				else:
					raise TypeError("Cannot read attributes of type {}".format(attr_type))
			
			for elem in dm.elements:
				if elem._is_placeholder: continue
				#print(elem.name,"@",in_file.tell())
				num_attributes = get_int(in_file)
				for i in range(num_attributes):
					start = in_file.tell()
					name = dm._string_dict.read_string(in_file)
					attr_type = _get_dmx_id_type(encoding,encoding_ver,get_byte(in_file))
					#print("\t",name,"@",start,attr_type)
					if attr_type in _dmxtypes:
						elem[name] = get_value(attr_type)
					elif attr_type in _dmxtypes_array:
						array_len = get_int(in_file)
						arr = elem[name] = attr_type()
						arr_item_type = _get_single_type(attr_type)
						for x in range(array_len):
							arr.append( get_value(arr_item_type,from_array=True) )
		
		dm._string_dict = None
		return dm
	finally:
		if in_file: in_file.close()
