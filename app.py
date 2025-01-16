# python3 /Users/ikermontane/Documents/Spotify/flask_website_spot/app.py
# Ctrl C to stop running

from flask import Flask, render_template, request, jsonify
import pandas as pd
from datetime import datetime, timedelta
import pytz

app = Flask(__name__)

# Load the dataset
path = "/Users/ikermontane/Documents/Spotify/spot_dash.csv"
df = pd.read_csv(path)

path1 = "/Users/ikermontane/Documents/Spotify/precomputed_weekly_data.csv"
fd = pd.read_csv(path1)

# Extract unique Regions and Countries
regions = df["Region"].dropna().str.strip().unique().tolist()
countries_by_region = df.groupby(df["Region"].str.strip())["Country_name"].unique().to_dict()

def get_effective_date():
    # Define the Mexico City timezone
    mexico_city_tz = pytz.timezone("America/Mexico_City")

    # Get the current time in the Mexico City timezone
    now = datetime.now(mexico_city_tz)

    # Determine the effective date
    if now.hour < 16 or (now.hour == 17 and now.minute < 30):
        # Before 4:30 PM, use the previous day's date
        effective_date = now - timedelta(days=1)
    else:
        # After 4:30 PM, use today's date
        effective_date = now

    # Return the date in 'YYYY-MM-DD' format
    return effective_date.strftime('%Y-%m-%d')

@app.route("/")
def home():
    # Prepare the regions list dynamically
    regions = (
        df["Region"]
        .dropna()  # Remove NaN entries
        .str.strip()  # Remove leading/trailing spaces
        .str.title()  # Capitalize region names
        .unique()
        .tolist()
    )

    # Exclude "Unknown" or other invalid entries
    regions = [region for region in regions if region.lower() != "unknown"]

    if "Global" not in regions:
        regions.insert(0, "Global")  # Ensure "Global" is at the top

    # Pass regions and other data to the template
    return render_template(
        "index.html",
        regions=regions,
        countries_by_region=countries_by_region,
        current_region="Global",  # Default to Global
    )

@app.route("/get_top_10_data", methods=["GET"])
def get_top_10_data():
    # Get selected filters
    selected_regions = request.args.getlist("region[]")  # Get multiple regions as a list
    selected_countries = request.args.getlist("country[]")  # Get multiple countries as a list

    # Get the effective date
    effective_date = get_effective_date()

    # Filter data by regions, countries, and date
    if "Global" in selected_regions:
        filtered_df = df[(df["Country_code"] == "GLB") & (df["Snapshot_date"] == effective_date)]
    else:
        filtered_df = df[(df["Region"].isin(selected_regions)) & (df["Snapshot_date"] == effective_date)]
        if selected_countries:
            filtered_df = filtered_df[filtered_df["Country_name"].isin(selected_countries)]

    # Handle case when no data is found
    if filtered_df.empty:
        return jsonify({"names": [], "scores": []})

    # Filter for songs in the top 10 Daily_rank values
    top_10_ranks_df = filtered_df[filtered_df["Daily_rank"] <= 10]

    # Calculate repetition score (number of occurrences in top 10)
    repetition_score = top_10_ranks_df["Name"].value_counts(normalize=False).reset_index()
    repetition_score.columns = ["Name", "Repetition_Score"]

    # Add popularity scores (normalized to 0-1 scale)
    popularity_scores = filtered_df.drop_duplicates(subset="Name")[["Name", "Popularity"]]
    popularity_scores["Popularity_Score"] = (
        (popularity_scores["Popularity"] - popularity_scores["Popularity"].min())
        / (popularity_scores["Popularity"].max() - popularity_scores["Popularity"].min())
    )

    # Merge repetition score and popularity score into a single dataframe
    scores_df = repetition_score.merge(popularity_scores, on="Name", how="left")

    # Calculate final score (65% repetition, 35% popularity)
    scores_df["Final_Score"] = (scores_df["Repetition_Score"] * 0.65) + (scores_df["Popularity_Score"] * 0.35)

    # Sort by final score and take the top 10
    top_10_songs = scores_df.sort_values(by="Final_Score", ascending=False).head(10)

    # Prepare data for the response
    data = {
        "names": top_10_songs["Name"].tolist(),
        "scores": top_10_songs["Final_Score"].tolist(),
    }
    return jsonify(data)

@app.route("/get_song_details", methods=["GET"])
def get_song_details():
    # Get song name and regions from the request
    song_name = request.args.get("name")
    selected_regions = request.args.getlist("region[]")
    selected_countries = request.args.getlist("country[]")

    # If Global is selected, include all regions
    if "Global" in selected_regions:
        selected_regions = ["Africa", "Asia", "America", "Europe", "Oceania"]

    # URL-decode the song name to match the dataset
    from urllib.parse import unquote
    song_name = unquote(song_name)

    # Get the effective date
    effective_date = get_effective_date()

    # Filter data for the selected regions, countries, and date
    filtered_df = df[df["Snapshot_date"] == effective_date]
    if selected_regions:
        filtered_df = filtered_df[filtered_df["Region"].isin(selected_regions)]
    if selected_countries:
        filtered_df = filtered_df[filtered_df["Country_name"].isin(selected_countries)]

    # Get details for the selected song
    song_details = filtered_df[filtered_df["Name"].str.strip() == song_name].iloc[0]
    appearances = int(
        filtered_df[
            (filtered_df["Name"].str.strip() == song_name) & (filtered_df["Daily_rank"] <= 10)
        ].shape[0]
    )
    popularity = float(song_details["Popularity"])
    artists = song_details["Artists"] if "Artists" in song_details else "Unknown"
    duration_ms = int(song_details["Duration_ms"]) if "Duration_ms" in song_details else 0
    explicit = bool(song_details["Is_explicit"]) if "Is_explicit" in song_details else False

    # Return the results as JSON
    return jsonify({
        "appearances": appearances,
        "popularity": popularity,
        "artists": artists,
        "duration_ms": duration_ms,
        "explicit": explicit
    })


@app.route("/get_countries", methods=["POST"])
def get_countries():
    selected_regions = request.json.get("regions", [])
    
    # If "Global" is selected, return all countries
    if "Global" in selected_regions or not selected_regions:
        available_countries = df["Country_name"].unique().tolist()
    else:
        # Otherwise, return countries in the selected regions
        available_countries = (
            df[df["Region"].isin(selected_regions)]["Country_name"].unique().tolist()
        )
    
    return jsonify({"countries": available_countries})

@app.route('/get_mode_data', methods=['POST'])
def get_mode_data():
    """
    Fetches the mode values (Major/Minor) for the requested songs.
    """
    song_names = request.json.get('names', [])
    filtered_df = df[df['Name'].isin(song_names)]
    mode_values = filtered_df['Mode'].tolist()  # Extract the Mode values
    return jsonify({'mode': mode_values})

@app.route('/get_time_series_data', methods=['POST'])
def get_time_series_data():
    """
    Retrieves precomputed weekly averages for the line chart based on the selected regions.
    """
    # Get selected regions from the request
    selected_regions = request.json.get('regions', [])

    # Define the five main regions
    main_regions = ['Africa', 'Asia', 'America', 'Europe', 'Oceania']

    if not selected_regions or "Global" in selected_regions or set(selected_regions) == set(main_regions):
        # Treat "Global" or all five regions as the same
        filtered_fd = fd[fd['Region'] == 'Global']
    else:
        # Generate the region combination key for filtering
        region_combination_key = ', '.join(sorted(selected_regions))  # Sort and join regions for consistency
        filtered_fd = fd[fd['Region'] == region_combination_key]

    # Handle case when no data is found
    if filtered_fd.empty:
        return jsonify({
            'week': [],
            'valence': [],
            'danceability': [],
            'energy': [],
        })

    # Prepare the response data
    response_data = {
        'week': filtered_fd['week'].tolist(),
        'valence': filtered_fd['Valence'].tolist(),
        'danceability': filtered_fd['Danceability'].tolist(),
        'energy': filtered_fd['Energy'].tolist(),
    }

    # Return the filtered data as JSON
    return jsonify(response_data)

if __name__ == "__main__":
    app.run(debug=True)
