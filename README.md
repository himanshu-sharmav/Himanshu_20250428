# Store Monitoring System
A backend system for monitoring store online/offline status and generating reports.

## Overview
This system monitors restaurant activity status and generates reports about their uptime and downtime during business hours. It provides REST APIs to trigger report generation and retrieve the generated reports.

## Features
- Asynchronous report generation with trigger + poll architecture
- Handles multiple time zones
- Considers business hours for uptime/downtime calculation
- Efficient data processing with batch operations
- Robust error handling and data validation

## Tech Stack
- Python 3.8+
- Flask (Web Framework)
- SQLAlchemy (ORM)
- Pandas (Data Processing)
- SQLite (Database)

## Project Structure


store-monitoring/
├── script.py # Main application code
├── requirements.txt # Python dependencies
├── sample_output.csv # Sample report output
├── README.md # Documentation
└── store-monitoring-data.zip # Input data


## Setup and Running
1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Place the data file `store-monitoring-data.zip` in the project directory

3. Run the application:
```bash
python3 script.py
```

4. Test the APIs:
```bash
# Generate a report
curl -X POST http://localhost:5000/trigger_report

# Get report status/download (replace <report_id> with the ID received)
curl http://localhost:5000/get_report?report_id=<report_id>
```

## API Documentation

### 1. Trigger Report Generation
- **Endpoint**: `/trigger_report`
- **Method**: POST
- **Response**: JSON containing report_id
```json
{
    "report_id": "e1f880ee-67e3-4877-b01b-8fc481816e2c"
}
```

### 2. Get Report Status/Download
- **Endpoint**: `/get_report`
- **Method**: GET
- **Query Parameters**: report_id
- **Response**: 
  - If running: Status message
  - If complete: CSV file
  - If error: Error message

## Implementation Details

### Data Processing
- Uses batch processing for efficient data handling
- Implements caching for frequently accessed data
- Handles timezone conversions correctly
- Robust error handling for data inconsistencies

### Business Hours Calculation
The system calculates uptime/downtime within business hours using the following logic:
1. Converts all timestamps to store's local timezone
2. Considers business hours for each day
3. Interpolates status between observations
4. Handles edge cases like missing timezone data

## Future Improvements
1. **Performance Optimization**
   - Implement Redis caching for frequently accessed data
   - Add database indexing for faster queries
   - Use parallel processing for report generation

2. **Scalability**
   - Implement horizontal scaling using microservices
   - Add load balancing
   - Use message queues for report generation

3. **Monitoring and Reliability**
   - Add comprehensive logging
   - Implement health checks
   - Add metrics collection
   - Set up monitoring alerts

4. **Additional Features**
   - Add authentication/authorization
   - Implement rate limiting
   - Add API versioning
   - Create a dashboard for report visualization

## Sample Output
A sample report output can be found in [sample_output.csv](sample_output.csv) in this repository.

[Link to video demo](https://www.loom.com/share/2ec126b96357447ca0a7377a3b66362f?sid=305a9d02-ab69-4c23-91b0-47dba49b4fe2)