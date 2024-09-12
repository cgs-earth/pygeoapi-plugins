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

`id_field` is the only field that is required to be labelled.

```yaml
providers:
  - type: feature
    name: pygeoapi_plugins.provider.geopandas_.GeoPandasProvider
    # Example data
    data: 'https://www.hydroshare.org/resource/3295a17b4cc24d34bd6a5c5aaf753c50/data/contents/hu02.gpkg'
    id_field: id
```

You can also use plain CSV and read in points by providing an `x_field` and `y_field` in the config the [same way you would with the default pygeoapi CSV provider](https://github.com/geopython/pygeoapi/blob/510875027e8483ce2916e7cf315fb6a7f6105807/pygeoapi-config.yml#L137).

## OGC API - Processes

Additional OGC API - Process are listed below

### Intersector

The intersection process uses OGC API - Features Part 3: Filtering to return CQL intersections of features.
An example configuration in a pygeoapi configuration is below.

```yaml
intersector:
  type: process
  processor:
    name: pygeoapi_plugins.process.intersect.IntersectionProcessor
```

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

## OGC API - Environmental Data Retrieval

### Sensorthings API

The EDR provider is implemented as the default for retrieving environmental data in a compliant manner with the OGC API - EDR specification. This ensures that spatial and temporal queries can be efficiently performed on the sensor data. Additionally, the OGC API - Features (OAF) provider is used to fill in the /items component of the API, allowing access to the Things (sensor devices) from the SensorThings API.

Both providers are configured together to offer a unified interface for sensor data access, while maintaining compliance with OGC standards. The EDR provider is responsible for the core environmental data retrieval, while the OAF provider exposes the sensor entities.

> **Note:** For more information on configuring the OAF provider, refer to the [SensorThings API](https://docs.pygeoapi.io/en/latest/data-publishing/ogcapi-features.html#sensorthings-api) documentation.

```yaml
providers:
  # EDR Provider for environmental data retrieval
  - type: edr
    name: pygeoapi_plugins.provider.sensorthings_edr.SensorThingsEDRProvider
    data: https://labs.waterdata.usgs.gov/sta/v1.1/

  # OAF Provider for exposing sensor entities (Things)
  - type: feature
    name: pygeoapi.provider.sensorthings.SensorThingsProvider
    data: https://labs.waterdata.usgs.gov/sta/v1.1/
    entity: Things
    title_field: name
```
