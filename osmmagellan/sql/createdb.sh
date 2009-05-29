#!/bin/sh

osm_username=osm
database_name=osm

## Drop db
sudo -u postgres dropdb $database_name

## Create db
sudo -u postgres createdb $database_name

## Prepare it for postgis
sudo -u postgres createlang plpgsql -d $database_name
sudo -u postgres psql $database_name -f /usr/share/postgresql-8.3-postgis/lwpostgis.sql
sudo -u postgres psql $database_name -f /usr/share/postgresql-8.3-postgis/spatial_ref_sys.sql

## grant rights
  (
        echo "GRANT ALL ON SCHEMA PUBLIC TO \"$osm_username\";"
        echo "GRANT ALL on geometry_columns TO \"$osm_username\";"
        echo "GRANT ALL on spatial_ref_sys TO \"$osm_username\";"
        echo "GRANT ALL ON SCHEMA PUBLIC TO \"$osm_username\";"
    ) | sudo -u postgres psql $quiet -Upostgres "$database_name"

## Create osm tables
psql $database_name -U osm < pgsql_simple_schema_0.6.sql


