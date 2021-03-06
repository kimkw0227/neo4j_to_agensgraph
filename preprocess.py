import sys
import re
import os.path
from subprocess import Popen, PIPE, STDOUT

unique_import_id={}
implicit_uii={}
multiple_vlabels={}
multiple_vlabels_dump={}
vertex_hash={}
UIL="'UNIQUE +IMPORT +LABEL'"
UII="'UNIQUE +IMPORT +ID'"
ipc=""
multiple_vlabel_cnt=0
use_agens=False
use_dump=False
mulv_label_name="AG_MULV_"
last_uii=0
last_uii_block=False
last_uii_begin_number=""

def set_multiple_vlabel(vertexes, s_property):
	global multiple_vlabel_cnt, multiple_vlabels, mulv_label_name
	top_vertex=mulv_label_name
	multiple_vlabel_cnt=int(multiple_vlabel_cnt) + 1
	top_vertex = top_vertex + str(multiple_vlabel_cnt)
	multiple_vlabels[vertexes] = str(top_vertex) + "\t" + str(s_property)
	return top_vertex

def set_multiple_vlabel_dump(s_id, vertexes, s_property):
	global multiple_vlabel_cnt, multiple_vlabels_dump, mulv_label_name
	s_str=set_multiple_vlabel(vertexes, s_property)
	top_vertex = mulv_label_name + str(multiple_vlabel_cnt)
	multiple_vlabels_dump[int(s_id)] = str(top_vertex) + "\t" + str(s_property)
	return s_str

def set_last_uii(s_id):
	global last_uii, last_uii_begin_number, last_uii_block, implicit_uii
	last_uii=s_id
	if last_uii_begin_number == "":
		last_uii_begin_number=last_uii
	else:
		if last_uii_block == False:
			size=len(implicit_uii)
			for key in implicit_uii.copy():
				val = implicit_uii.get(key)
				del implicit_uii[key]
				new_key = int(last_uii_begin_number) - ( int(size) - int(key) )
				implicit_uii[int(new_key)] = val
			last_uii_block = True

def proc(ls):
	global multiple_vlabels, last_uii, implicit_uii
	if re.search('^(CREATE|DROP) +CONSTRAINT .+UNIQUE +IMPORT', ls, flags=re.IGNORECASE):
		return ""

	if re.search('^MATCH .+ REMOVE .+', ls, flags=re.IGNORECASE):
		return ""

	ls = re.sub("'", "''", ls)
	ls = re.sub(r'\\"([\},])', r"\\\\'\1", ls)
	ls = re.sub(r'([^\\])(`|")', r"\1'", ls)
	ls = re.sub(r'\\"', '"', ls)
	ls = re.sub(r'^\s*BEGIN\s*$', r'BEGIN;\n', ls, flags=re.IGNORECASE)
	ls = re.sub(r'^\s*COMMIT\s*$', r'COMMIT;\n', ls, flags=re.IGNORECASE)

	st = r"^CREATE \(:'(\S+)' +\{(.+)\}\);"
	m1 = re.search(st, ls, flags=re.IGNORECASE)
	if m1:
		vlabel = m1.group(1)
		s_property = m1.group(2)
		if not re.search(UIL + r" +\{(.+)," + UII, ls):
			last_uii = int(last_uii) + 1
			implicit_uii[int(last_uii)] = str(vlabel) + "\t" + str(s_property)

	st = r"CREATE +\(:'(\S+)':"+UIL+" +\{"+UII+":(\d+)\}\);"
	m1 = re.search(st, ls, flags=re.IGNORECASE)
	if m1:
		vlabel = m1.group(1)
		s_id = m1.group(2)
		set_last_uii(s_id)
		if re.search("':'", vlabel):
			vlabel = re.sub("':'", ":", vlabel)
			vlabel = set_multiple_vlabel(str(vlabel), "")
			unique_import_id[s_id] = str(vlabel) + "\t"
			return ""
		unique_import_id[s_id] = str(vlabel) + "\t"
		ls = re.sub(r":" + UIL + " +.+", ");", ls)

	st = r"CREATE +\(:'(\S+)':" + UIL + r" +\{(.+), " + UII + r':(\d+)\}\);'
	m1 = re.search(st, ls, flags=re.IGNORECASE)
	if m1:
		vlabel = m1.group(1)
		keyval = m1.group(2)
		s_id = m1.group(3)
		set_last_uii(s_id)
		if re.search("':'", vlabel):
			vlabel = re.sub("':'", ":", vlabel)
			vlabel = set_multiple_vlabel(str(vlabel), keyval)
			unique_import_id[s_id] = str(vlabel) + "\t" + str(keyval)
			return ""
		unique_import_id[s_id] = str(vlabel) + "\t" + str(keyval)
		ls = re.sub(r"^CREATE +\(:'(\S+)':" + UIL + r" +\{", 'CREATE (:' + str(vlabel) + ' {', ls, flags=re.IGNORECASE) 
		ls = re.sub(r", +" + UII + r":\d+\}", "}", ls)

	if re.search(r"^SCHEMA +AWAIT", ls, re.IGNORECASE):
		if multiple_vlabels:
			ls = "BEGIN;\n"
			for key in sorted(multiple_vlabels):
				val = multiple_vlabels.get(key)
				val1, s_property = val.split("\t")
				prev=""
				for vlabel in key.split(":"):
					if re.search("\S", s_property):
						ls = ls + "CREATE (:" + str(vlabel) + " { " + str(s_property) + " });\n"
					else:
						if prev != vlabel:
							ls = ls + "CREATE VLABEL " + str(vlabel) + ";\n"
					prev = vlabel

				ls = ls + "CREATE VLABEL " + str(val1) + " INHERITS ("
				for vlabel in key.split(":"):
					ls = ls + str(vlabel) + ", "
				ls = re.sub(r", $", "", ls)
				ls = ls + ");\n"

			ls = ls + "COMMIT;\n"
			multiple_vlabels = {}
		else:
			return ""

	st = r"^(?i)MATCH +\(n1:" + UIL + r"(\{" + UII + ":\d+\})\), +\(n2:" + UIL + "({" + UII + ":\d+\})\)"
	m1 = re.search(st, ls, re.IGNORECASE)
	if m1:
		n1 = m1.group(1)
		n2 = m1.group(2)
		ls = re.sub(UIL, "", ls)
		ls = re.sub(r"\[r:'(\S+)'\]", r"[r:\1]", ls, flags=re.IGNORECASE)
		ls = re.sub(r"\[:'(\S+)'\]", r"[:\1]", ls, flags=re.IGNORECASE)
		m2 = re.search(r'(\d+)', n1)
		if m2:
			s_id = unique_import_id.get(m2.group(1))
			if s_id == None:
				s_id = implicit_uii.get(int(m2.group(1)))
				if s_id == None:
					s_id = "\t"
			s_id = re.sub(r"\t", " {", str(s_id)) + '}'
			ls = re.sub(n1, s_id, ls, flags=re.IGNORECASE)
		m2 = re.search(r'(\d+)', n2)
		if m2:
			s_id = unique_import_id.get(m2.group(1))
			if s_id == None:
				s_id = implicit_uii.get(int(m2.group(1)))
				if s_id == None:
					s_id = "\t"
			s_id = re.sub(r"\t", " {", str(s_id)) + '}'

			ls = re.sub(n2, s_id, ls, flags=re.IGNORECASE)

	while (1):
		st=UIL + '\{' + UII + '\:(\d+)}'
		m1 = re.search(st, ls, flags=re.IGNORECASE)
		if m1:
			s_id = m1.group(1)
			val = unique_import_id.get(s_id)
			if val == None:
				val = implicit_uii.get(int(s_id))
				if val == None:
					val = "\t"
			val = re.sub(r"\t", " {", str(val)) + '}'

			ls = re.sub(UIL + '\{' + UII + '\:('+s_id+')}', val, ls, flags=re.IGNORECASE)
		else:
			break

	st = r"^CREATE +\(:'(\S+)'"
	m1 = re.search(st, ls, flags=re.IGNORECASE)
	if m1:
		ls = re.sub(st, r'CREATE (:\1', ls, flags=re.IGNORECASE)

	st = r"^CREATE +INDEX +ON +:"
	m1 = re.search(st, ls, flags=re.IGNORECASE)
	if m1:
		ls = re.sub(st, 'CREATE PROPERTY INDEX ON ', ls, flags=re.IGNORECASE)
		ls = re.sub("'", '', ls)

	st = r"^CREATE +CONSTRAINT +ON +\(\S+:'(\S+)'\) +ASSERT +\S+\.'(\S+)'"
	m1 = re.search(st, ls, flags=re.IGNORECASE)
	if m1:
		ls = re.sub(st, r"CREATE CONSTRAINT ON \1 ASSERT \2", ls, flags=re.IGNORECASE)

	st = r"^MATCH +\(n1:'*(\S+)'*\s*\{"
	m1 = re.search(st, ls, flags=re.IGNORECASE)
	if m1:
		val = m1.group(1)
		val = re.sub(r"'$", "", val)
		ls = re.sub(r"^MATCH +\(n1:'*(\S+)'*\s*\{", "MATCH (n1:" + str(val) + " {", ls, flags=re.IGNORECASE)
		st = r" +\(n2:'*(\S+)'*\s*\{"
		m2 = re.search(st, ls, flags=re.IGNORECASE)
		if m2:
			val = m2.group(1)
			val = re.sub(r"'$", "", val)
			ls = re.sub(r" +\(n2:'*(\S+)'*\s*\{", " (n2:" + str(val) + " {", ls, flags=re.IGNORECASE)
		ls = re.sub(r"\[:'(\S+)'\]", r"[:\1]", ls, flags=re.IGNORECASE)
		ls = re.sub(r"\[:'(\S+)' ", r"[:\1 ", ls, flags=re.IGNORECASE)

	return ls

def proc_dump(ls):
	global multiple_vlabels, multiple_vlabels_dump, set_multiple_vlabe_dump
	mlabel_ls=""
	if not re.search('^\s*(begin|commit|create )', ls, flags=re.IGNORECASE):
		return ""

	ls = re.sub("'", "''", ls)
	ls = re.sub(r'\\"([\},])', r"\\\\'\1", ls)
	ls = re.sub(r'([^\\])(`|")', r"\1'", ls)
	ls = re.sub(r'\\"', '"', ls)
	ls = re.sub(r'^\s*BEGIN\s*$', r'BEGIN;\n', ls, flags=re.IGNORECASE)
	ls = re.sub(r'^\s*COMMIT\s*$', r'COMMIT;\n', ls, flags=re.IGNORECASE)

        # vertex with multilabels (without property)
	st = r"^create +\(_(\d+):(\S+)\)"
	m1 = re.search(st, ls, flags=re.IGNORECASE)
	if m1:
		vnum = m1.group(1)
		vlabels = m1.group(2)
		if re.search("':'", vlabels):
			vlabels = re.sub(r"^'", "", vlabels)
			vlabels = re.sub(r"'$", "", vlabels)
			lbls = vlabels.split("':'")
			lbls.sort
			vertexes=""
			for item in lbls:
				vertexes = vertexes + str(item) + ":"
			vertexes = re.sub(":$", "", vertexes)
			set_multiple_vlabel_dump(int(vnum), str(vertexes), "")
			return ""

	# vertex with multilabels (with property)
	st = r"create +\(_(\d+):(\S+) +\{(.+)\}\)"
	m1 = re.search(st, ls, flags=re.IGNORECASE)
	if m1:
		vnum = m1.group(1)
		vlabels = m1.group(2)
		vprop = m1.group(3)
		if re.search("':'", vlabels):
			vlabels = re.sub(r"^'", "", vlabels)
			vlabels = re.sub(r"'$", "", vlabels)
			lbls = vlabels.split("':'")
			lbls.sort
			vertexes=""
			for item in lbls:
				vertexes = vertexes + str(item) + ":"
			vertexes = re.sub(":$", "", vertexes)
			set_multiple_vlabel_dump(int(vnum), str(vertexes), vprop)
			return ""

	st = r"^create +\(_\d+\)-"
	m1 = re.search(st, ls, flags=re.IGNORECASE)
	if multiple_vlabels:
		for key in sorted(multiple_vlabels):
			val = multiple_vlabels.get(key)
			val1, s_property = val.split("\t")
			prev=""
			for vlabel in key.split(":"):
				if re.search("\S", s_property):
					mlabel_ls = mlabel_ls + "CREATE (:" + str(vlabel) + " { " + str(s_property) + " });\n"
				else:
					if prev != vlabel:
						mlabel_ls = mlabel_ls + "CREATE VLABEL " + str(vlabel) + ";\n"
				prev = vlabel

			mlabel_ls = mlabel_ls + "CREATE VLABEL " + str(val1) + " INHERITS ("
			for vlabel in key.split(":"):
				mlabel_ls = mlabel_ls + str(vlabel) + ", "
			mlabel_ls = re.sub(r", $", "", mlabel_ls)
			mlabel_ls = mlabel_ls + ");\n"

		multiple_vlabels = {}


	# vertex with property
	st = r"^create +\(_(\d+):'(\S+)' +\{(.+)\}\)\s*$"
	m1 = re.search(st, ls, flags=re.IGNORECASE)
	if m1:
		vertex_hash[int(m1.group(1))] = str(m1.group(2)) + "\t" + str(m1.group(3))
		ls = "CREATE (:" + str(m1.group(2)) + " {" + str(m1.group(3)) + "});"

	# vertex without property
	st = r"^create +\(_(\d+):'(\S+)'\)\s*$"
	m1 = re.search(st, ls, flags=re.IGNORECASE)
	if m1:
		vertex_hash[int(m1.group(1))] = str(m1.group(2)) + "\t"
		ls = "CREATE (:" + str(m1.group(2)) + ");"

	# edge with property
	st = r"^create +\(_(\d+)\)-\[:(\S+) +\{(.+)\}\]->\(_(\d+)\)\s*$"
	m1 = re.search(st, ls, flags=re.IGNORECASE)
	if m1:
		vnum1=m1.group(1)
		elabel=m1.group(2)
		eprop=m1.group(3)
		vnum2=m1.group(4)
		vertex1=vertex_hash.get(int(vnum1))
		vertex2=vertex_hash.get(int(vnum2))
		vertex1_label=""
		vertex1_prop=""
		vertex2_label=""
		vertex2_prop=""
		if vertex1:
			vertex1_label, vertex1_prop = vertex1.split("\t")
		else:
			s_str = multiple_vlabels_dump.get(int(vnum1))
			vertex1_label, vertex1_prop = s_str.split("\t")
		if vertex2:
			vertex2_label, vertex2_prop = vertex2.split("\t")
		else:
			s_str = multiple_vlabels_dump.get(int(vnum2))
			vertex2_label, vertex2_prop = s_str.split("\t")
		elabel=re.sub(r"^\s*'(.+)'\s*$", r"\1", elabel)
		ls = "MATCH (n1:" + str(vertex1_label) + " {" + str(vertex1_prop) + "}), (n2:" + str(vertex2_label) + " {" + str(vertex2_prop) + "}) CREATE (n1)-[:" + str(elabel) + " {" + str(eprop) + "}]->(n2);"

	# edge without property
	st = r"^create +\(_(\d+)\)-\[:(\S+)\]->\(_(\d+)\)"
	m1 = re.search(st, ls, flags=re.IGNORECASE)
	if m1:
		vnum1=m1.group(1)
		elabel=m1.group(2)
		vnum2=m1.group(3)
		vertex1=vertex_hash.get(int(vnum1))
		vertex2=vertex_hash.get(int(vnum2))
		vertex1_label=""
		vertex1_prop=""
		vertex2_label=""
		vertex2_prop=""
		if vertex1:
			vertex1_label, vertex1_prop = vertex1.split("\t")
		else:
			s_str = multiple_vlabels_dump.get(int(vnum1))
			vertex1_label, vertex1_prop = s_str.split("\t")
		if vertex2:
			vertex2_label, vertex2_prop = vertex2.split("\t")
		else:
			s_str = multiple_vlabels_dump.get(int(vnum2))
			vertex2_label, vertex2_prop = s_str.split("\t")
		elabel=re.sub(r"^\s*'(.+)'\s*$", r"\1", elabel)
		ls = "MATCH (n1:" + str(vertex1_label) + " {" + str(vertex1_prop) + "}), (n2:" + str(vertex2_label) + " {" + str(vertex2_prop) + "}) CREATE (n1)-[:" + str(elabel) + "]->(n2);"

	if not mlabel_ls == "":
		ls = mlabel_ls + ls
	return ls

def load_file(filename):
	f = open(filename, 'r')
	x = f.readlines()
	f.close()
	return x

def make_graph_st(graph_name):
	return "DROP GRAPH IF EXISTS "+graph_name+" CASCADE;\nCREATE GRAPH "+graph_name+";\nSET GRAPH_PATH="+graph_name+";"

def out(ls):
	global use_agens, use_dump
	line=""
	m1 = re.search(r'^\s*$', ls)
	if ls == "" or m1:
		return
	if use_dump:
		line=proc_dump(ls)
	else:
		line=proc(ls)
	m1 = re.search(r'^\s*$', line)
	if line == "" or m1:
		return
	line=re.sub("(\r|\n)+$", "", line)
	if use_agens:
		global ipc
		line = re.sub("$", "\n", line)
		ipc.stdin.write(line.encode())
	else:
		print(line)

def main():
	global use_agens, graph_st, use_dump
	graph_name=""
	s_file=""
	graph_st=""
	opt=""

	for arg in sys.argv[1:]:
		if arg == "--import-to-agens":
			use_agens=True
			continue
		if arg == "--use-dump":
			use_dump=True
			continue
		m1 = re.search(r'^--graph=(\S+)$', arg)
		if m1:
			graph_name=m1.group(1)
			continue
		m1 = re.search(r'^(--)(dbname|host|port|username)(=\S+)$', arg)
		if m1:
			opt = " " + m1.group(0)
			continue
		m1 = re.search(r'^(--)(no-password|password)$', arg)
		if m1:
			opt = " " + m1.group(0)
			continue
		m1 = re.search(r'^--', arg)
		m2 = re.search(r'^--(h|help)$', arg)
		if m1 or m2:
			print("USAGE: python " + sys.argv[0] + " [--import-to-agens] [--graph=GRAPH_NAME] [--use-dump] [--help] [filename (optional if STDIN is provided)]")
			print("   Additional optional parameters for the AgensGraph integration:")
			print("      [--dbname=DBNAME] : Database name")
			print("      [--host=HOST]     : Hostname or IP")
			print("      [--port=PORT]     : Port")
			print("      [--username=USER] : Username")
			print("      [--no-password]   : No password")
			print("      [--password]      : Ask password (should happen automatically)")
			exit(0)
		s_file=arg
	if not graph_name:
		print("Please specify the --graph= parameter to initialize the graph repository.")
		exit(1)
	if s_file:
		if not os.path.isfile(s_file):
			print("File not found: " + s_file)
			exit(1)
	graph_st=make_graph_st(graph_name)
	if use_agens:
		global ipc
		ret = ""
		not_avail = "agens client is not available"
		try:
			ret = Popen(['agens', '--help'], stdin=None, stdout=PIPE, stderr=STDOUT)
		except OSError:
			print(not_avail)
			exit(1)
		ret.wait()
		if ret.returncode != 0:
			print(not_avail)
			exit(1)
		ipc = Popen(['agens', opt], stdin=PIPE, stderr=STDOUT)
		graph_st = re.sub("$", "\n", graph_st)
		ipc.stdin.write(graph_st.encode())
	else:
		print(graph_st)

	if not s_file == "":
		x=load_file(s_file)
		for ls in x:
			out(ls)
	else:
		for ls in sys.stdin:
			out(ls)
	if use_agens:
		ipc.stdin.close()

main()

