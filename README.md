# pygeoapi-plugins

[pygeoapi](https://pygeoapi.io) plugins developed by the Center for Geospatial Solutions

## OGC API - Features

Additional OGC API - Feature providers are listed below, along with a matrix of supported query parameters.

| Provider           | Property Filters/Display | Result Type  | BBox | Datetime | Sort By | Skip Geometry | CQL | Transactions | CRS |
| ------------------ | ------------------------ | ------------ | ---- | -------- | ------- | ------------- | --- | ------------ | --- |
| `CKAN`             | ✅/✅                    | results/hits | ❌   | ❌       | ✅      | ✅            | ❌  | ❌           | ✅  |
| `PsuedoPostgreSQL` | ✅/✅                    | results/hits | ✅   | ✅       | ✅      | ✅            | ✅  | ❌           | ✅  |
| `SPARQL`           | ❌/✅                    | results/hits | ❌   | ❌       | ❌      | ❌            | ❌  | ❌           | ❌  |
| `GeoPandas`        | ✅/✅                    | results/hits | ✅   | ✅       | ✅      | ✅            | ❌  | ✅           | ✅  |

The provider names listed in the table are only accessible in [internetofwater/pygeoapi](https://github.com/internetofwater/pygeoapi), otherwise the full python path is required.

### CKAN

The CKAN Provider enables OGC API - Feature support at the collection level for a specific resource within the datastore-search endpoints of CKAN instances.
It allows you to integrate CKAN resources into your pygeoapi instance.
The provider definition for the CKAN Provider includes configuration options specific to CKAN.
To use the CKAN Provider, you need to specify `pygeoapi_plugins.provider.ckan.CKANProvider` as the provider's name.

```yaml
providers:
  - type: feature
    name: pygeoapi_plugins.provider.ckan.CKANProvider
    data: https://catalog.newmexicowaterdata.org/api/3/action/datastore_search
    resource_id: 08369d21-520b-439e-97e3-5ecb50737887
    id_field: _id
    x_field: LONDD
    y_field: LATDD
```

In this example, the CKAN Provider is configured to work with the specified CKAN resource.

- `data`: The URL endpoint for the datastore search API of the CKAN instance.
- `resource_id`: The identifier of the specific CKAN resource you want to access within the datastore.
- `id_field`: The field that serves as the unique identifier for features in the CKAN resource.
- `x_field`: The field representing the X-coordinate (longitude) for the features in the CKAN resource.
- `y_field`: The field representing the Y-coordinate (latitude) for the features in the CKAN resource.

### PseudoPostgresSQL

The PseudoPostgresSQL Provider adds a simple capacity to the PostgresSQL Provider in pygeoapi core - faster counting.
This is done by performing a pseudo-count on tables exceeding a definable limit.
The limit is defined using the PSEUDO_COUNT_LIMIT environment variable.
To use the PseudoPostgresSQL Provider, you need to specify `pygeoapi_plugins.provider.postgresql.PseudoPostgreSQLProvider` as the provider's name.

### SPARQL

The SPARQL Provider is a wrapper for any pygeoapi feature provider that provides additional context, allowing integration of SPARQL-based data sources into a pygeoapi instance.
By wrapping another feature provider, the SPARQL Provider inherits queryable capacities from the wrapped feature provider - adding SPARQL context to each resulting feature.
The provider definition for the SPARQL Provider is similar to that of the wrapped provider, with the addition of specific SPARQL-related configuration options.
To use the SPARQL Provider, you need to specify `pygeoapi_plugins.provider.sparql.SPARQLProvider` as the provider's name.

```yaml
providers:
  - # Normal pygeoapi provider configuration
    type: feature
    data: /pygeoapi_plugins/tests/data/places.csv
    id_field: index
    geometry:
      x_field: lon
      y_field: lat
    #
    name: pygeoapi_plugins.provider.sparql.SPARQLProvider
    sparql_provider: CSV # Name of provider SPARQL is wrapping
    sparql_query:
      endpoint: https://dbpedia.org/sparql
      bind:
        name: uri
        variable: '?subject'
      prefixes:
        '': <http://dbpedia.org/resource/>
        dbpedia2: <http://dbpedia.org/property/>
        dbo: <http://dbpedia.org/ontology/>
      where:
        - subject: '?subject'
          predicate: dbo:populationTotal
          object: '?population'
        - subject: '?subject'
          predicate: dbo:country
          object: '?country'
        - subject: '?subject'
          predicate: '<http://dbpedia.org/property/leaderName>'
          object: '?leader'
      filter:
        - 'FILTER (isIRI(?leader) || isLiteral(?leader))'
```

In this example, the SPARQL Provider wraps the GeoJSON Provider.
The SPARQL Provider only uses variables prefixed with sparql\_ in the configuration.

- `data`: The path to the data file used by the wrapped provider (GeoJSON Provider in this case).
- `id_field`: The field that serves as the unique identifier for features in the data.
- `sparql_provider`: The name of the provider that will handle the SPARQL query results (GeoJSON Provider in this case).
- `sparql_query`: The SPARQL object holding the content of the SPARQL query.
  - `endpoint`: The SPARQL variable representing the graph IRI in the query.
  - `bind`:
    - `name`: Field in the wrapped properties block to query the graph with
    - `variable`: The SPARQL variable used for querying (e.g., ?subject).
      prefixes:
  - `prefixes`: Optional dictionary defining the prefixes used in the SPARQL query.
  - `where`: A list of mappings that define the WHERE clause of the SPARQL query. Each mapping includes:
    - `subject`: The subject of the triple pattern.
    - `predicate`: The predicate of the triple pattern.
    - `object`: The object of the triple pattern.
  - `filter`: A list of SPARQL filter expressions to apply to the results.

### GeoPandas

The GeoPandas Provider enables OGC API - Feature support using GeoPandas as the backend. This integration can read in data files in [any of the geospatial formats supported by GeoPandas](https://geopandas.org/en/stable/docs/user_guide/io.html#supported-drivers-file-formats).

`id_field` is the only field that is required to be labeled.

```yaml
providers:
  - type: feature
    name: pygeoapi_plugins.provider.geopandas_.GeoPandasProvider
    # Example data
    data: 'https://www.hydroshare.org/resource/3295a17b4cc24d34bd6a5c5aaf753c50/data/contents/hu02.gpkg'
    id_field: id
```

You can also use plain CSV and read in points by providing an `x_field` and `y_field` in the config the [same way you would with the default pygeoapi CSV provider](https://github.com/geopython/pygeoapi/blob/510875027e8483ce2916e7cf315fb6a7f6105807/pygeoapi-config.yml#L137).

## OGC API - Tiles

Additional OGC API - Tile providers are listed below

### MVT PostgreSQL

The MVT PostgreSQL Provider extends the core provider, to include additional supports for rendering features
efficiently at low zoom. The threshold for applying limits can be controlled with the configuration option
`disable_at_z`. The default value for the zoom threshold is 6.

The first way to filter the features that are rendered is by setting a minimum pixel size. The
configuration option `min_pixel` provider will drop features that are less than a pixel in the
rendered tile. The default value for minimum pixel size is 512. The following configuration
would render half pixel features until zoom level 10.

```yaml
providers:
  - type: tile
    name: pygeoapi_plugins.provider.mvt_postgresql.MVTPostgreSQLProvider_
    ...
    disable_at_a: 10
    mix_pixel: 256 # a full pixel in the tile
```

The second way to filter the features that are rendered in a tile is using a modified CQL expression. The
CQL expression can be used to determine render priority based on non-geographic attributes of a feature
The following configuration would only render features with a population larger than 100,000:

```yaml
providers:
  - type: tile
    name: pygeoapi_plugins.provider.mvt_postgresql.MVTPostgreSQLProvider_
    ...
    tile_threshold: "population > 100000"
```

The CQL expression can be formatted with a `z` value (minimum zoom is 1). This allows the parameter filter to be dynamic
based on the zoom level of the tile. The following configuration would render tiles of successively
smaller populations for every subsequent zoom level increase:

```yaml
providers:
  - type: tile
    name: pygeoapi_plugins.provider.mvt_postgresql.MVTPostgreSQLProvider_
    ...
    disable_at_z: 5
    tile_threshold: "population_served_count > 200000 / ({z} * 2)"
    # z{0}: population_served_count > 100000
    # z{1}: population_served_count > 100000
    # z{2}: population_served_count > 50000
    # z{3}: population_served_count > 33333
    # z{4}: population_served_count > 25000
```

The configuration option `tile_limit` can be specified to enforce a maximum number of features in a single tile.
This will apply to all tiles regardless of if the other filters are enabled by `disable_at_z`. Features will be ordered
by the size of there bounding box, pruning the smallest feature until the feature limit is met for the tile.

```yaml
providers:
  - type: tile
    name: pygeoapi_plugins.provider.mvt_postgresql.MVTPostgreSQLProvider_
    ...
    disable_at_z: 0 # Apply no CQL or Pixel Size filter
    tile_limit: 1000 # No more than 1000 features in a single tile
```

### MVT PostgreSQL with Caching

There are two additional Postgres based MVT providers with caching of tiles to prevent significant server load
on tile generation at low zoom levels. Both providers use the configuration option `disable_cache_at_z` to
prevent storing tiles at high zoom levels if undesired.

#### Filesystem Cache

The filesystem cache uses a local filesystem to store pbf blobs in a typical z/y/x directory tree.

```yaml
providers:
  - type: tile
    name: pygeoapi_plugins.provider.mvt_cache.MVTPostgresFilesystem
    ...
    cache_directory: /tmp/mvt_cache # Default directory if not specified
    disable_cache_at_z: 6 # Default value to disable caching if not specified
```

#### PostgreSQL Table Cache

The table cache uses an external table to store pbf blobs in a typical z/y/x relational database.
Make sure the credentials have access to update the table and write if necessary.

```yaml
providers:
  - type: tile
    name: pygeoapi_plugins.provider.mvt_cache.MVTPostgresCache
    ...
    table: osm_waterways
    mvt_table: osm_waterways_mvt # Default table is table with `_mvt` appended
    disable_cache_at_z: 25 # Cache everything (eventually)
```

## OGC API - Processes

Additional OGC API - Processes are listed below

### Intersector

The intersection process uses GDAL Python bindings to return features from a 
collection using an existing Geospatial OGR based file as the spatial mask.

An example configuration in a pygeoapi configuration is below.

```yaml
intersector:
  type: process
  processor:
    name: pygeoapi_plugins.process.intersect.IntersectionProcessor
```

* **collection** is always required
* **url** or **file** is required
  - **url** is the remote source of the Geospatial file
  - **file** is the encoded bytes of the Geospatial file

This plugin is used in https:/reference.geoconnex.us/.

### Sitemap Generator

The Sitemap Generator process makes use of the XML formatter and OGC API - Features to generate a sitemap of the pygeoapi instance.
This can be used with the python package [sitemap-generator](https://github.com/cgs-earth/sitemap-generator) to generate a sitemap index.
An example configuration in a pygeoapi configuration is below.

```yaml
sitemap-generator:
  type: process
  processor:
    name: pygeoapi_plugins.process.sitemap.SitemapProcessor
```
