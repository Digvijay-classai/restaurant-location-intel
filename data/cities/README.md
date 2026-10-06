# City boundaries

Drop `<city>.geojson` here to override the bounding-box fallback. The
loader accepts a FeatureCollection, a single Feature, or a bare
Geometry; multiple polygons are unioned.

Good sources:
- [INE city shapefile portal](https://www.ine.es/censos2011_datos/cen11_datos_resultados_seccen.htm)
- [Overpass turbo](https://overpass-turbo.eu) query:
  `relation["name"="Madrid"]["admin_level"=8]; out geom;`
