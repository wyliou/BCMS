import { StrictMode } from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';

// Reason: Import i18n here to ensure initialization before React tree renders
import './i18n';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
