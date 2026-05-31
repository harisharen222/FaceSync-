// globals.js — Polyfills loaded at the very beginning of the application lifecycle.
// This is imported before any other business logic modules to prevent ES6 hoisting crashes.

if (typeof global.TextEncoder === 'undefined') {
  class TextEncoder {
    encode(string) {
      const length = string.length;
      const bytes = new Uint8Array(length * 3);
      let offset = 0;
      for (let i = 0; i < length; i++) {
        let codePoint = string.codePointAt(i);
        if (codePoint < 128) {
          bytes[offset++] = codePoint;
        } else if (codePoint < 2048) {
          bytes[offset++] = (codePoint >> 6) | 192;
          bytes[offset++] = (codePoint & 63) | 128;
        } else if (codePoint < 65536) {
          bytes[offset++] = (codePoint >> 12) | 224;
          bytes[offset++] = ((codePoint >> 6) & 63) | 128;
          bytes[offset++] = (codePoint & 63) | 128;
        } else {
          bytes[offset++] = (codePoint >> 18) | 240;
          bytes[offset++] = ((codePoint >> 12) & 63) | 128;
          bytes[offset++] = ((codePoint >> 6) & 63) | 128;
          bytes[offset++] = (codePoint & 63) | 128;
          i++;
        }
      }
      return bytes.slice(0, offset);
    }
  }

  class TextDecoder {
    decode(bytes) {
      if (!bytes) return '';
      let string = '';
      let i = 0;
      while (i < bytes.length) {
        let byte = bytes[i++];
        if (byte < 128) {
          string += String.fromCodePoint(byte);
        } else if (byte > 191 && byte < 224) {
          let byte2 = bytes[i++];
          string += String.fromCodePoint(((byte & 31) << 6) | (byte2 & 63));
        } else if (byte > 223 && byte < 240) {
          let byte2 = bytes[i++];
          let byte3 = bytes[i++];
          string += String.fromCodePoint(((byte & 15) << 12) | ((byte2 & 63) << 6) | (byte3 & 63));
        } else {
          let byte2 = bytes[i++];
          let byte3 = bytes[i++];
          let byte4 = bytes[i++];
          string += String.fromCodePoint(((byte & 7) << 18) | ((byte2 & 63) << 12) | ((byte3 & 63) << 6) | (byte4 & 63));
        }
      }
      return string;
    }
  }

  global.TextEncoder = TextEncoder;
  global.TextDecoder = TextDecoder;
  console.log('Global TextEncoder and TextDecoder polyfills injected successfully ✓');
}
