# pygeoapi-plugins

pygeoapi plugins developed by the Center for Geospatial Solutions

Not intended to run standalone - intended to be installed during pygeoapi installation

## OGC API - Features

CGS additional feature providers are listed below, along with a matric of supported query parameters.

| Provider | Property Filters/Display | Result Type | BBox | Datetime | Sort By | Skip Geometry | CQL | Transactions | CRS |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `CKAN` | ✅/✅ | results/hits | ❌ | ❌ | ✅ | ✅ | ❌ | ❌ | ✅ |
| `SPARQL` | ❌/✅ | results | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ | ✅ |

The SPARQL Provider wraps a feature provider to add additional context, passing all query parameters to the wrapped provider.

## OGC API - Processes

CGS provides an intersection process, using OGC API - Features Part 3: Filtering to return CQL intersections of features.
An example configuration in a pygeoapi configuration is below.

```
  intersector:
    type: process
    processor:
      name: pygeoapi_plugins.process.intersect.IntersectionProcessor
```


This plugin is used in https://nhdpv2-census.internetofwater.app/.
