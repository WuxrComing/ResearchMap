import * as React from "react";

type Props = {
  icon: string;
  size: number;
  children?: React.ReactNode;
  className?: string;
};

const Icon = ({ icon = "app", size = 4, className = "" }: Props) => {
  const sizeClass = `h-${size} w-${size} ${className}`;

  if (icon === "app") {
    return (
      <svg
        className={`${sizeClass} inline-block`}
        xmlns="http://www.w3.org/2000/svg"
        fill="currentColor"
        viewBox="0 0 290 264"
      >
        <path
          d="M112.233 104.244C106.455 104.242 100.778 105.756 95.7684 108.635C90.7586 111.513 86.5912 115.655 83.6823 120.647L0 264H38.456C44.2308 263.999 49.9048 262.486 54.9137 259.613C59.9226 256.739 64.0919 252.603 67.0068 247.618L86.2185 214.713L97.1033 196.079L141.807 119.548L150.733 104.244H112.233Z"
          fill="url(#paint0_linear)"
        />
        <path
          d="M111.547 33.2857L130.813 0L212.939 144.278C215.795 149.3 217.285 154.982 217.262 160.759C217.239 166.535 215.704 172.205 212.809 177.205L193.532 210.49L111.417 66.2122C108.559 61.1911 107.068 55.5088 107.091 49.7316C107.114 43.9544 108.65 38.284 111.547 33.2857Z"
          fill="url(#paint1_linear)"
        />
        <path
          d="M289.285 245.714H123.281C117.498 245.714 111.815 244.199 106.8 241.319C101.785 238.439 97.6121 234.295 94.6976 229.3L86.1748 214.714L97.0596 196.079H241.348C247.134 196.075 252.82 197.588 257.837 200.468C262.855 203.349 267.029 207.495 269.943 212.493L289.285 245.714Z"
          fill="url(#paint2_linear)"
        />
        <defs>
          <linearGradient id="paint0_linear" x1="116.173" y1="107.901" x2="37.3131" y2="255.118" gradientUnits="userSpaceOnUse">
            <stop stopColor="#2314CC" />
            <stop offset="0.22" stopColor="#234CE4" />
            <stop offset="1" stopColor="#4081FF" />
          </linearGradient>
          <linearGradient id="paint1_linear" x1="200.792" y1="184.508" x2="134.199" y2="47.8169" gradientUnits="userSpaceOnUse">
            <stop stopColor="#7215D4" />
            <stop offset="0.11" stopColor="#7554D5" />
            <stop offset="0.56" stopColor="#9E8AE9" />
            <stop offset="1" stopColor="#CC99FF" />
          </linearGradient>
          <linearGradient id="paint2_linear" x1="107.651" y1="220.896" x2="271.108" y2="220.896" gradientUnits="userSpaceOnUse">
            <stop stopColor="#2E31F0" />
            <stop offset="0.2" stopColor="#4081FF" />
            <stop offset="0.39" stopColor="#848EE5" />
            <stop offset="0.49" stopColor="#8183E2" />
            <stop offset="0.65" stopColor="#7866DA" />
            <stop offset="0.75" stopColor="#7251D4" />
          </linearGradient>
        </defs>
      </svg>
    );
  }

  return (
    <svg className={`${sizeClass} inline-block`} xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24">
      <path d="M1 3.488c0-1.926 4.656-3.488 10-3.488 5.345 0 10 1.562 10 3.488s-4.655 3.487-10 3.487c-5.344 0-10-1.561-10-3.487zm10 9.158c5.345 0 10-1.562 10-3.487v-2.44c-2.418 1.738-7.005 2.256-10 2.256-3.006 0-7.588-.523-10-2.256v2.44c0 1.926 4.656 3.487 10 3.487zm0 5.665c.34 0 .678-.007 1.011-.019.045-1.407.537-2.7 1.342-3.745-.839.067-1.643.1-2.353.1-3.006 0-7.588-.523-10-2.256v2.434c0 1.925 4.656 3.486 10 3.486zm1.254 1.97c-.438.02-.861.03-1.254.03-2.995 0-7.582-.518-10-2.256v2.458c0 1.925 4.656 3.487 10 3.487 1.284 0 2.526-.092 3.676-.256-1.155-.844-2.02-2.055-2.422-3.463zm10.746-1.781c0 2.485-2.017 4.5-4.5 4.5s-4.5-2.015-4.5-4.5 2.017-4.5 4.5-4.5 4.5 2.015 4.5 4.5zm-2.166-1.289l-2.063.557.916-1.925-1.387.392-1.466 3.034 1.739-.472-1.177 2.545 3.438-4.131z" />
    </svg>
  );
};

export default Icon;
