#!/usr/bin/make

clean:
	 @while read -r charm_temp_dir; do \
	     rm -rfv $$charm_temp_dir; \
	 done < charms.txt
