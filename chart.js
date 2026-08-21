const statusEl = document.getElementById('status');
const startEl = document.getElementById('start');
const endEl = document.getElementById('end');
const profitChart = document.getElementById('profitChart');
const refreshBtn = document.getElementById('refreshBtn');
 
function setStatus(type, msg){
    statusEl.className = `alert alert-${type}py-2`;
    statusEl.textContent = msg;
}

function isoDaysAgo(days){
    const date = new Date();
    date.setDate(date.getDate()-days);
    const y = date.getFullYear();
    const m = String(date.getMonth()+1).padStart(2, '0');
    const d = String(date.getDate()).padStart(2, '0');
    return `${y}-${m}-${d}`;
}

startEl.value = isoDaysAgo(30);
endEl.value = isoDaysAgo(0);

const chart = new Chart(profitChart, {
    type: "bar",
    data: {labels: [], datasets: [{label: "Profit", data: [], backgroundColor: "rgba(75, 192, 192, 0.2)", borderColor: "rgba(75, 192, 192, 1)", borderWidth: 1}]},
    options: { responsive: true, mainAspectRatio: false, scales: {y: {beginAtZero: false}}}
});

async function load(){
    const start = startEl.value;
    const end = endEl.value;

    if(!start || !end){
        setStatus('warning', 'Please select a valid date range.');
        return;

    if(start > end){
        setStatus('warning', 'Start date cannot be after end date.');
        return;
    }

    setStatus('info', 'loading data...');

    try{
        const response = await fetch(`/api/profit?start=${start}&end=${end}`);

        if (!response.ok){
            throw new Error("Could not load data from server.");
       
        }

        const result = await response.json();
        const data = result.data;

        const labels = [];
        const profits = [];

    for (const item of data){
            labels.push(item.date);
            profits.push(item.profit);
        }

        if (labels.length === 0){
            chart.data.labels = [];
            chart.data.datasets[0].data = [];
            chart.update();
            
            setStatus('warning', 'No data available for the selected date range.');
            return;
        }

        chart.data.labels = labels;
        chart.data.datasets[0].data = profits;
        chart.update();

        setStatus('success', 'Data loaded successfully.');  
    } catch (error){
        setStatus('danger', `Error loading data: ${error.message}`);
        console.log ("Error loading chart data:", error);
    }
    }
 }

 startEl.addEventListener('change', load);
 endEl.addEventListener('change', load);
 refreshBtn.addEventListener('click', load);

 load();
