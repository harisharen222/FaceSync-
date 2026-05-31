import React from 'react';
import {AttendanceScreen} from './src/screens/AttendanceScreen';

export default function App(): React.JSX.Element {
  return (
    <AttendanceScreen
      backendBaseUrl="http://13.48.24.253:8000"
      deviceId="saraw-iphone-16"
      deviceJwt="eyJhbGciOiJSUzI1NiIsImtpZCI6Im5oYWktcnMyNTYtMSIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJuaGFpLWF1dGgtc2VydmljZSIsInN1YiI6InNhcmF3LWlwaG9uZS0xNiIsInN1Yl90eXBlIjoiMjQ4NWNjOTQtOWYwMi00YTQzLTk1ZTMtN2JlODI0NzRhNWQ1IiwiaWF0IjoxNzgwMjMyODc0LCJleHAiOjE3ODAyMzQ2NzQsInRva2VuX3R5cGUiOiJhY2Nlc3MiLCJzaXRlX2NvZGUiOiJTSVRFXzEyMyJ9.cQdONYIiLri_6UoGw7kr3N_woZt_mB7PvDixBq2z_4yTQvIfSxKT-PRxlPlrBL47SPNPWAaWqelkDXQZ4OCElLNF2VEdE-kYzJG_OJIWds2TTbqyQI3ONEBITG5PR3J6KfFMHXcF0KC2QNCrqK2N8EFKCJSfOJQCmRXtZwM9-hcSPsL51XBu9F5YbAP0BIyg1yhxu6un_NJ7uZ4UUIskvfAYbdqj_EI3X-pH7HrARSHQriQIB6S8pgduarMbi92Gsbwb5dmLGMnEuN_ubMSvoDADxUFQYS2UY8zo_fBq2_OzpkQ6_R2swOLa5vs922xNJlStWfu2zq7mzUROS1F-Sw"
    />
  );
}
