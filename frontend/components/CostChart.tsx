import React from 'react';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  Title,
  Tooltip,
  Legend
} from 'chart.js';
import { Bar } from 'react-chartjs-2';

ChartJS.register(CategoryScale, LinearScale, BarElement, Title, Tooltip, Legend);

interface CostChartProps {
  data: Array<Record<string, any>>;
  labelKey: string;
  valueKey: string;
  title?: string;
}

const CostChart: React.FC<CostChartProps> = ({
  data,
  labelKey,
  valueKey,
  title = 'Cost Breakdown'
}) => {
  const labels = data.map(item => item[labelKey] as string);
  const values = data.map(item => Number(item[valueKey]));

  const chartData = {
    labels,
    datasets: [
      {
        label: valueKey,
        data: values,
        backgroundColor: 'rgba(25, 118, 210, 0.7)',
      }
    ]
  };

  const options = {
    responsive: true,
    plugins: {
      legend: { position: 'top' as const },
      title: { display: true, text: title }
    }
  };

  return <Bar data={chartData} options={options} />;
};

export default CostChart;