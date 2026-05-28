import React from 'react';
import {AttendanceScreen} from './src/screens/AttendanceScreen';

export default function App(): React.JSX.Element {
  return (
    <AttendanceScreen
      backendBaseUrl="https://YOUR_AWS_API_URL"
      deviceId="YOUR_DEVICE_ID"
      deviceJwt="YOUR_DEVICE_JWT"
    />
  );
}
