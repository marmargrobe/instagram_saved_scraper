# python3.12 -m venv .venv_data_maps
# source .venv_data_maps/bin/activate
# pip3 install follium


# Here's an example of how you can use folium to create a simple map:
import folium 
map = folium.Map(location=[21.39, 84.29], zoom_start=13)

points = [[20.5920749, 85.8017591], [20.5218388, 85.7341526], [21.3470154, 83.6320212]]

point = points[0]

# for single point
folium.Marker(point, popup='My Home').add_to(map)


# for multiple points
for point in points:
    folium.Marker(point, popup='Point').add_to(map)

# Now, our Google Map is ready with these points, to visualized it, you just need to call the created map object.

map


# To plot circle on the map

for point in points:
  folium.CircleMarker(point,radius = 5,color = 'red',fill = True).add_to(map)