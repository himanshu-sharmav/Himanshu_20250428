# Store Monitoring System

A robust backend system for monitoring store (restaurant) activity status and generating comprehensive reports about their uptime and downtime during business hours.

## Overview

This system processes store activity data to track when stores are online or offline, considering their specific business hours and time zones. It provides a RESTful API interface to generate and retrieve reports about store activity metrics.

## Key Features

- **Real-time Status Monitoring**
  - Tracks store online/offline status
  - Handles multiple time zones accurately
  - Considers local business hours for each store

- **Asynchronous Report Generation**
  - Trigger + Poll architecture for non-blocking report generation
  - Background processing with ThreadPoolExecutor
  - Progress tracking and error handling

- **Efficient Data Processing**
  - Batch processing for large datasets
  - In-memory SQLite database for fast operations
  - Optimized timezone conversions

- **Robust Error Handling**
  - Comprehensive exception management
  - Data validation and sanitization
  - Detailed error reporting

## Technical Architecture

### Database Models

1. **StoreStatus**
   - Tracks store activity status
   - Fields: store_id, timestamp_utc, status (active/inactive)

2. **BusinessHours**
   - Stores operating hours for each store
   - Fields: store_id, day_of_week, start_time_local, end_time_local

3. **StoreTimezone**
   - Manages store timezone information
   - Fields: store_id, timezone_str

4. **Report**
   - Tracks report generation status
   - Fields: id, status (Running/Complete/Error), filename

### API Endpoints

1. **Trigger Report Generation**
   ```
   POST /trigger_report
   
   Response:
   {
       "report_id": "uuid-string"
   }
   ```

2. **Get Report Status/Download**
   ```
   GET /get_report?report_id=<report_id>
   
   Responses:
   - Running: {"status": "Running"}
   - Complete: CSV file download
   - Error: {"status": "Error"}
   ```

## Setup Instructions

1. **Environment Setup**
   ```bash
   # Create and activate virtual environment (optional but recommended)
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   
   # Install dependencies
   pip install -r requirements.txt
   ```

2. **Data Preparation**
   - Place `store-monitoring-data.zip` in the project root directory
   - The zip file should contain:
     - `store_status.csv`: Store activity logs
     - `business_hours.csv`: Store operating hours
     - `store_timezone.csv`: Store timezone information

3. **Running the Application**
   ```bash
   python script.py
   ```
   The server will start on `http://localhost:5000`

## Dependencies

Flask==3.0.0
Flask-SQLAlchemy==3.1.1
pandas==2.1.1
pytz==2024.1
python-dotenv==1.0.1
sqlalchemy==2.0.31
sqlite3==3.43.0

## Project Structure

Himanshu_20250428/
├── script.py # Main application code
├── requirements.txt # Python dependencies
├── sample_output.csv # Sample report output
├── README.md # Documentation
└── store-monitoring-data.zip # Input data

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