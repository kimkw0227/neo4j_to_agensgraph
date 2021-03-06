use strict;
use IPC::Open2;
my %unique_import_id;
my %implicit_uii;
my %multiple_vlabels;
my %multiple_vlabels_dump;
my %vertex_hash;
my $UIL="'UNIQUE +IMPORT +LABEL'";
my $UII="'UNIQUE +IMPORT +ID'";
my ($pid, $out, $in);
my $multiple_vlabel_cnt=0;
my $use_agens=0;
my $use_dump=0;
my $mulv_label_name="AG_MULV_";
my $last_uii=0;
my $last_uii_block=0;
my $last_uii_begin_number;

sub set_multiple_vlabel {
	my ($vertexes, $property) = @_;
	my $top_vertex = $mulv_label_name;
	$multiple_vlabel_cnt++;
	$top_vertex .= $multiple_vlabel_cnt;
	$multiple_vlabels{$vertexes} = $top_vertex . "\t" . $property;
	return $top_vertex;
}

sub set_multiple_vlabel_dump {
	my ($id, $vertexes, $property) = @_;
	my $str = set_multiple_vlabel($vertexes, $property);
	my $top_vertex = $mulv_label_name . $multiple_vlabel_cnt;
	$multiple_vlabels_dump{$id} = $top_vertex . "\t" . $property;
	return $str;
}

sub set_last_uii {
	my $id = shift;
	$last_uii = $id;
	if (!$last_uii_begin_number) {
		$last_uii_begin_number=$last_uii;
	} else {
		if ($last_uii_block eq 0) {
			my $size = keys %implicit_uii;
			foreach my $key (keys %implicit_uii) {
				my $val = $implicit_uii{$key};
				my $new_key;
				delete $implicit_uii{$key};
				$new_key = $last_uii_begin_number - ($size - $key);
				$implicit_uii{$new_key} = $val;
			}
			$last_uii_block=1;
		}
	}
}

sub proc {
	my $ls = shift;
	return "" if ($ls =~ /^(CREATE|DROP) +CONSTRAINT .+UNIQUE +IMPORT/i);
	return "" if ($ls =~ /^MATCH .+ REMOVE .+/i);

	$ls =~ s/'/''/g;
	$ls =~ s/\\"([\},])/\\\\'$1/g;
	$ls =~ s/([^\\])(`|")/$1'/g;
	$ls =~ s/\\"/"/g;
	$ls =~ s/^\s*BEGIN\s*$/BEGIN;/i;
	$ls =~ s/^\s*COMMIT\s*$/COMMIT;/i;

	if ($ls =~/^CREATE \(:'(\S+)' +\{(.+)\}\);/i) {
		my $vlabel = $1;
		my $property = $2;
		if ($ls !~ /$UIL +\{(.+), $UII/) {
			$last_uii++;
			$implicit_uii{$last_uii} = "$vlabel\t$property";
		}
	};

	if ($ls =~ /CREATE +\(:'(\S+)':$UIL +\{$UII:(\d+)\}\);/i) {
		my $vlabel = $1;
		my $id = $2;
		set_last_uii($id);
		if ($vlabel =~ /':'/) {
			$vlabel =~ s/':'/:/g;
			$vlabel = set_multiple_vlabel($vlabel, "");
			$unique_import_id{$id} = "$vlabel\t";
			return "";
		}
		$unique_import_id{$id} = "$vlabel\t";
		$ls =~ s/:$UIL +.+/);/;
	}

	if ($ls =~ /CREATE +\(:'(\S+)':$UIL +\{(.+), $UII:(\d+)\}\);/i) {
		my $vlabel = $1;
		my $keyval = $2;
		my $id = $3;
		set_last_uii($id);
		if ($vlabel =~ /':'/) {
			$vlabel =~ s/':'/:/g;
			$vlabel = set_multiple_vlabel($vlabel, $keyval);
			$unique_import_id{$id} = $vlabel . "\t" . $keyval;
			return "";
		}
		$unique_import_id{$id} = $vlabel . "\t" . $keyval;
		$ls =~ s/CREATE +\(:'(\S+)':$UIL +\{/CREATE (:$1 {/i;
		$ls =~ s/, +$UII:\d+\}/\}/i;
	}

	if ($ls =~ /^SCHEMA +AWAIT/i) {
		if (%multiple_vlabels) {
			$ls = "BEGIN;\n";
			foreach my $key (sort keys %multiple_vlabels) {
				my $val = $multiple_vlabels{$key};
				my ($val1, $property) = (split /\t/, $val);
				my $prev;

				foreach my $vlabel (sort split /:/, $key) {
					if ($property =~ /\S/) {
						$ls .= "CREATE (:$vlabel { $property });\n";
					} else {
						if ($prev ne $vlabel) {
							$ls .= "CREATE VLABEL $vlabel;\n";
						}
					}
					$prev = $vlabel;
				}
				$ls .= "CREATE VLABEL $val1 INHERITS (";
				foreach my $vlabel (sort split /:/, $key) {
					$ls .= "$vlabel, ";
				}
				$ls =~ s/, $//;
				$ls .= ");\n";
			}
			$ls .= "COMMIT;\n";
			undef %multiple_vlabels;
		} else {
			return "";
		}
	}

	if ($ls =~ /^MATCH +\(n1:$UIL(\{$UII:\d+\})\), +\(n2:$UIL(\{$UII:\d+\})\)/i) {
		my $n1 = $1;
		my $n2 = $2;
		$ls =~ s/$UIL//ig;
		$ls =~ s/\[r:'(\S+)'\]/[r:$1]/i;
		$ls =~ s/\[:'(\S+)'\]/[:$1]/i;
		if ($n1 =~ /(\d+)/) {
			my $num = $1;
			my $id = $unique_import_id{$num};
			if (!$id) {
				$id = $implicit_uii{$num};
				if(!$id) {
					$id = "\t";
				}
			}
			$id =~ s/\t/ {/;
			$id .= '}';
			$ls =~ s/$n1/$id/i;
		}
		if ($n2 =~ /(\d+)/) {
			my $num = $1;
			my $id = $unique_import_id{$num};
			if (!$id) {
				$id = $implicit_uii{$num};
				if(!$id) {
					$id = "\t";
				}
			}
			$id =~ s/\t/ {/;
			$id .= '}';
			$ls =~ s/$n2/$id/i;
		}
	}

	while (1) {
		if ($ls =~ /$UIL\{$UII\:(\d+)}/) {
			my $id = $1;
			my $val = $unique_import_id{$id};
			if (!$val) {
				$val = $implicit_uii{$id};
				if(!$val) {
					$val = "\t";
				}
			}
			$val =~ s/\t/ {/;
			$val .= '}';
			$ls =~ s/$UIL\{$UII\:($id)}/$val/;
		} else {
			last;
		}
	}

	if ($ls =~ /^CREATE +\(:'(\S+)'/i) {
		$ls =~ s/^CREATE +\(:'(\S+)'/CREATE (:$1/i;
	}
	if ($ls =~ /^CREATE +INDEX +ON +:/i) {
		$ls =~ s/^CREATE +INDEX +ON +:/CREATE PROPERTY INDEX ON /i;
		$ls =~ s/'//g;
	}
	if ($ls =~ /^CREATE +CONSTRAINT +ON +\(\S+:'(\S+)'\) +ASSERT +\S+\.'(\S+)'/i) {
		$ls =~ s/^CREATE +CONSTRAINT +ON +\(\S+:'(\S+)'\) +ASSERT +\S+\.'(\S+)'/CREATE CONSTRAINT ON $1 ASSERT $2/i;
	}
	if ($ls =~ /^MATCH +\(n1:'*(\S+)'*\s*\{/i) {
		my $val = $1;
		$val =~ s/'$//;
		$ls =~ s/^MATCH +\(n1:'*(\S+)'*\s*\{/MATCH (n1:$val {/i;
		if ($ls =~ / +\(n2:'*(\S+)'*\s*\{/) {
			$val = $1;
			$val =~ s/'$//;
			$ls =~ s/ +\(n2:'*(\S+)'*\s*\{/ (n2:$val {/i;
		}
		$ls =~ s/\[:'(\S+)'\]/[:$1]/i;
		$ls =~ s/\[:'(\S+)' /[:$1 /i;
	}
	$ls =~ s/\s*$//;
	return $ls;
}

sub proc_dump {
	my $ls = shift;
	my $mlabel_ls;
	return unless ($ls =~ /^\s*(begin|commit|create )/i);
	$ls =~ s/'/''/g;
	$ls =~ s/\\"([\},])/\\\\'$1/g;
	$ls =~ s/([^\\])(`|")/$1'/g;
	$ls =~ s/\\"/"/g;
	$ls =~ s/^\s*BEGIN\s*$/BEGIN;/i;
	$ls =~ s/^\s*COMMIT\s*$/COMMIT;/i;

	# vertex with multilabels (without property)
	if ($ls =~ /^create +\(_(\d+):(\S+)\)/i) {
		my $vnum = $1;
		my $vlabels = $2;
		if ($vlabels =~ /':'/) {
			$vlabels =~ s/^'(.+)'$/$1/;
			my @lbls = sort (split /':'/, $vlabels);
			my $vertexes;
			foreach my $item (@lbls) {
				$vertexes .= $item . ":";
			}
			$vertexes =~ s/:$//;
			set_multiple_vlabel_dump($vnum, $vertexes, "");
			return "";
		}
	}

	# vertex with multilabels (with property)
	if ($ls =~ /^create +\(_(\d+):(\S+) +\{(.+)\}\)/i) {
		my $vnum = $1;
		my $vlabels = $2;
		my $vprop = $3;
		if ($vlabels =~ /':'/) {
			$vlabels =~ s/^'(.+)'$/$1/;
			my @lbls = sort (split /':'/, $vlabels);
			my $vertexes;
			foreach my $item (@lbls) {
				$vertexes .= $item . ":";
			}
			$vertexes =~ s/:$//;
			set_multiple_vlabel_dump($vnum, $vertexes, $vprop);
			return "";
		}
	}

	if ($ls =~ /^create +\(_\d+\)-/i) {
		if (%multiple_vlabels) {
			foreach my $key (sort keys %multiple_vlabels) {
				my $val = $multiple_vlabels{$key};
				my ($val1, $property) = (split /\t/, $val);
				my $prev;

				foreach my $vlabel (sort split /:/, $key) {
					if ($property =~ /\S/) {
						$mlabel_ls .= "CREATE (:$vlabel { $property });\n";
					} else {
						if ($prev ne $vlabel) {
							$mlabel_ls .= "CREATE VLABEL $vlabel;\n";
						}
					}
					$prev = $vlabel;
				}
				$mlabel_ls .= "CREATE VLABEL $val1 INHERITS (";
				foreach my $vlabel (sort split /:/, $key) {
					$mlabel_ls .= "$vlabel, ";
				}
				$mlabel_ls =~ s/, $//;
				$mlabel_ls .= ");\n";
			}
			undef %multiple_vlabels;
		}
	}

	# vertex with property
	if ($ls =~ /^create +\(_(\d+):'(\S+)' +\{(.+)\}\)\s*$/i) {
		$vertex_hash{$1} = "$2\t$3";
		$ls = "CREATE (:$2 {$3});";
	}
	# vertex without property
	if ($ls =~ /^create +\(_(\d+):'(\S+)'\)\s*$/i) {
		$vertex_hash{$1} = "$2\t";
		$ls = "CREATE (:$2);";
	}

	# edge with property
	if ($ls =~ /^create +\(_(\d+)\)-\[:(\S+) +\{(.+)\}\]->\(_(\d+)\)\s*$/i) {
		my $vnum1=$1;
		my $elabel=$2;
		my $eprop=$3;
		my $vnum2=$4;
		my $vertex1 = $vertex_hash{$vnum1};
		my $vertex2 = $vertex_hash{$vnum2};
		my ($vertex1_label, $vertex1_prop);
		my ($vertex2_label, $vertex2_prop);
		if ($vertex1) {
			($vertex1_label, $vertex1_prop) = (split /\t/, $vertex1);
		} else {
			my $str = $multiple_vlabels_dump{$vnum1};
			($vertex1_label, $vertex1_prop) = (split /\t/, $str);
		}
		if ($vertex2) {
			($vertex2_label, $vertex2_prop) = (split /\t/, $vertex2);
		} else {
			my $str = $multiple_vlabels_dump{$vnum2};
			($vertex2_label, $vertex2_prop) = (split /\t/, $str);
		}
		$elabel =~ s/^\s*'(.+)'\s*$/$1/;
		$ls = "MATCH (n1:$vertex1_label {$vertex1_prop}), (n2:$vertex2_label {$vertex2_prop}) CREATE (n1)-[:$elabel {$eprop}]->(n2);";
	}

	# edge without property
	if ($ls =~ /^create +\(_(\d+)\)-\[:(\S+)\]->\(_(\d+)\)/) {
		my $vnum1=$1;
		my $elabel=$2;
		my $vnum2=$3;
		my $vertex1 = $vertex_hash{$vnum1};
		my $vertex2 = $vertex_hash{$vnum2};
		my ($vertex1_label, $vertex1_prop);
		my ($vertex2_label, $vertex2_prop);
		if ($vertex1) {
			($vertex1_label, $vertex1_prop) = (split /\t/, $vertex1);
		} else {
			my $str = $multiple_vlabels_dump{$vnum1};
			($vertex1_label, $vertex1_prop) = (split /\t/, $str);
		}
		if ($vertex2) {
			($vertex2_label, $vertex2_prop) = (split /\t/, $vertex2);
		} else {
			my $str = $multiple_vlabels_dump{$vnum2};
			($vertex2_label, $vertex2_prop) = (split /\t/, $str);
		}
		$elabel =~ s/^\s*'(.+)'\s*$/$1/;
		$ls = "MATCH (n1:$vertex1_label {$vertex1_prop}), (n2:$vertex2_label {$vertex2_prop}) CREATE (n1)-[:$elabel]->(n2);";

	}

	$ls =~ s/\s*$//;
	if ($mlabel_ls) {
		$ls = $mlabel_ls . $ls;
	}
	return $ls;
}

sub load_file {
	my $filename = shift;
	unless ( -f $filename ) {
		printf("File not found: $filename\n");
		exit 1;
	}
	open my $in, '<:raw', $filename or die("Check the file: $filename\n");
	local $/;
	my $contents = <$in>;
	close($in);
	return $contents;
}

sub make_graph_st {
	my $graph_name = shift;
	return "DROP GRAPH IF EXISTS $graph_name CASCADE;\nCREATE GRAPH $graph_name;\nSET GRAPH_PATH=$graph_name;";
}

sub out {
	my $ls = shift;
	my $line;
	return if ($ls =~ /^\s*$/);
	if ($use_dump) {
		$line = proc_dump($ls);
	} else {
		$line = proc($ls);
	}
	return if ($line =~ /^\s*$/);
	if ($use_agens) {
		my $msg;
		print $in "$line\n";
		$msg = <$out>;
		print $msg;
	} else {
		printf("%s\n", $line);
	}
}

sub main {
	my $graph_name;
	my $file;
	my $graph_st;
	my $opt;
	foreach my $arg (@ARGV) {
		if ($arg =~ /^--import-to-agens$/) {
			$use_agens=1;
			next;
		}
		if ($arg =~ /^--use-dump$/) {
			$use_dump=1;
			next;
		}

		if ($arg =~ /^--graph=(\S+)$/) {
			$graph_name=$1;
			next;
		}
		if ($arg =~ /^(--)(dbname|host|port|username)(=\S+)$/) {
			$opt.=" " . $1 . $2 . $3;
			next;
		}
		if ($arg =~ /^(--)(no-password|password)$/) {
			$opt.=" " . $1 . $2;
			next;
		}
		if ($arg =~ /^--/ || $arg =~ /^--(h|help)$/) {
			printf("USAGE: perl $0 [--import-to-agens] [--graph=GRAPH_NAME] [--use-dump] [--help] [filename (optional if STDIN is provided)]\n");
			printf("   Additional optional parameters for the AgensGraph integration:\n");
			printf("      [--dbname=DBNAME] : Database name\n");
			printf("      [--host=HOST]     : Hostname or IP\n");
			printf("      [--port=PORT]     : Port\n");
			printf("      [--username=USER] : Username\n");
			printf("      [--no-password]   : No password\n");
			printf("      [--password]      : Ask password (should happen automatically)\n");
			exit 0;
		}
		$file=$arg;
	}

	if (!$graph_name) {
		printf("Please specify the --graph= parameter to initialize the graph repository.\n");
		exit 1;
	}

	if ($file) {
		if ( ! -f $file ) {
			printf("File not found: %s\n", $file);
			exit 1;
		}
	}
	$graph_st = make_graph_st($graph_name);
	if ($use_agens) {
		if ($^O eq 'MSWin32' || $^O eq 'cygwin' || $^O eq 'dos') {
			`agens --help >nul 2>&1`;
		} else {
			`agens --help >/dev/null 2>&1`;
		}
		if ($? ne 0) {
			printf("agens client is not available.\n");
			exit 1;
		}
		$pid = open2 $out, $in, "agens $opt";
		die "$0: open2: $!" unless defined $pid;
		print $in $graph_st . "\n";
		my $msg = <$out>;
		print $msg;
	} else {
		printf("%s\n", $graph_st);
	}
	if ($file) {
		foreach my $ls (split /\n/, load_file($file)) {
			out($ls);
		}
	} else {
		while (<STDIN>) {
			out($_);
		}
	}
	if ($use_agens) {
		close $in or warn "$0: close: $!";  
		close $out or warn "$0: close: $!";
	}
}

main();

