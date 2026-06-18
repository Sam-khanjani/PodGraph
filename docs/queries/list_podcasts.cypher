// All podcasts in the graph
MATCH (p:Podcast)
RETURN p.name AS podcast, p.host AS host;