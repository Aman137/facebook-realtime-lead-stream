$headers = @{ "X-API-Key" = "development-key" }
$events = @(
    @{
        source = "demo"
        source_message_id = "demo-001"
        group_name = "Frisco Neighbors"
        author = "Sample User"
        text = "Can anyone recommend a realtor? We are moving to Frisco and want to buy a home."
        post_url = "https://example.com/posts/demo-001"
    },
    @{
        source = "demo"
        source_message_id = "demo-002"
        group_name = "Dallas Homeowners"
        author = "Sample User"
        text = "Need a licensed roofer ASAP before closing. Who do you recommend?"
        post_url = "https://example.com/posts/demo-002"
    },
    @{
        source = "demo"
        source_message_id = "demo-003"
        group_name = "Neighborhood Chat"
        author = "Sample User"
        text = "I already found someone and am no longer looking for a contractor."
        post_url = "https://example.com/posts/demo-003"
    }
)

foreach ($event in $events) {
    $json = $event | ConvertTo-Json
    Invoke-RestMethod -Uri "http://localhost:8000/events" -Method Post `
        -Headers $headers -ContentType "application/json" -Body $json
}

