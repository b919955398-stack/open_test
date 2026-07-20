\NeedsTeXFormat{LaTeX2e}
\ProvidesClass{grid-link-appendix-template}[2024/02/07 Grid-Link appendix template]

\LoadClass[12pt, oneside]{book}

\RequirePackage{graphicx}
\RequirePackage{pdflscape}
\RequirePackage{graphicx}
\RequirePackage{xcolor}
\RequirePackage{ragged2e}
\RequirePackage{anyfontsize}
\RequirePackage{fancyhdr}
\RequirePackage{lipsum}
\RequirePackage{csvsimple-l3}
\RequirePackage{adjustbox}
\RequirePackage{titlesec}
\RequirePackage{marginnote}
\RequirePackage{booktabs}
\RequirePackage{longtable}
\RequirePackage{tabularx}
\RequirePackage{filecontents}
\RequirePackage{makecell}
\RequirePackage{underscore}
\RequirePackage{float}
\RequirePackage{amsmath}
\RequirePackage[hidelinks]{hyperref}
\RequirePackage{fontspec}
\RequirePackage{tabularray}
\RequirePackage{colortbl}
\RequirePackage{sectsty}
\RequirePackage{lastpage}
\RequirePackage[RPvoltages]{circuitikz}
\RequirePackage[absolute,overlay]{textpos}

\RequirePackage[usegeometry]{typearea}% before geometry!
\RequirePackage[
a4paper, 
margin=0.5in, 
top=0.9in, 
bottom=0.9in,
footskip=0.1in,
]{geometry}

\newcommand*{\useportrait}{%
	\clearpage
	\KOMAoptions{paper=portrait,DIV=current}%switch to portrait
	\newgeometry{% geometry settings for portrait
		left=0.5in, right=0.5in, top=0.6in, bottom=1.25in,headheight=23pt,includehead
	}%
	\fancyhfoffset{0pt}% <- recalculate head and foot width for fancyhdr
}
\newcommand*{\uselandscape}{%
	\clearpage
	\KOMAoptions{paper=landscape,DIV=current}%switch to landscape
	\newgeometry{% geometry settings for landscape
		left=0.5in, right=0.5in, top=0.6in, bottom=1.2in,headheight=23pt,includehead, footskip=1in
	}%
	\fancyhfoffset{0pt}% recalculate head and foot width for fancyhdr
}

\fancypagestyle{plain}{% Redefine plain page style for landscape pages
	\fancyhf{}% clear all fields
	\renewcommand{\headrulewidth}{1.0pt} % Thickness of the line under the header
	\setlength{\headheight}{32pt}
	% Set the color of the headrule
	\renewcommand{\headrule}{%
		\color{logogreen}\vskip0.1in% Add 1 inch of space between header and header rule
		\hrule width\headwidth height\headrulewidth \vskip-\headrulewidth%
	}%
	
	% Right side (logo)
	\fancyhead[R]{\includegraphics[width=1.2cm]{report-assets/logo-simplified-small.png}}
	
	
	% Left side (two lines of left-aligned text)
	\fancyhead[L]{%
		\parbox[b]{\textwidth\color{logogreen}}{%
			\raggedright
			\project \\
			\@title
		}%
	}
	
	% Left side text in the footer
	\fancyfoot[L]{\color{logogreen}CONNECTING YOUR PROJECTS | GRID-LINK PTY LTD}
	% Right side page number in the footer for main matter pages
	\fancyfoot[R]{\if@mainmatter\thepage\ / \pageref{LastPage}\else\Roman{page}\fi}
}

% Apply the header style to all pages
\pagestyle{plain}


%\RequirePackage[margin=0in, paperwidth=8.27in, paperheight=11.69in]{geometry}
\definecolor{logogreen}{RGB}{100, 150, 75}
\definecolor{logoblue}{RGB}{49, 161, 191}
\definecolor{chapterheadingblue}{RGB}{39, 41, 54}
\definecolor{tableheaderblue}{RGB}{41, 49, 80}
\definecolor{tablesubheadergrey}{RGB}{127, 127, 127}
\definecolor{tablefirstcolgrey}{RGB}{242, 242, 242}

% Variables
\newcommand{\project}[1]{\renewcommand{\project}{#1}}
\newcommand{\client}[1]{\renewcommand{\client}{#1}}
\newcommand{\docnumber}[1]{\renewcommand{\docnumber}{#1}}
\newcommand{\issueddate}[1]{\renewcommand{\issueddate}{#1}}
\newcommand{\revision}[1]{\renewcommand{\revision}{#1}}
\newcommand{\revisionhistorycsvpath}[1]{\renewcommand{\revisionhistorycsvpath}{#1}}

% Defined fonts
\setmainfont{Ubuntu}
\newcommand{\covertitlefont}{\fontsize{40}{42}\bfseries\selectfont\textcolor{logogreen}}
\newcommand{\coversubtitlefont}{\fontsize{20}{30}\selectfont\textcolor{logogreen}}
\newcommand{\coverlabelfont}{\fontsize{15}{26}\selectfont\textcolor{logogreen}}
\newcommand{\covervaluefont}{\fontsize{15}{26}\selectfont\textcolor{black}}
\newcommand{\footerfontbold}{\fontsize{13}{16}\bfseries\selectfont\textcolor{logogreen}}
\newcommand{\footerfontnormal}{\fontsize{13}{16}\selectfont\textcolor{logogreen}}

% Change how chapter titles display
\titleformat{\chapter}[hang] 
{\normalfont\huge\bfseries\color{chapterheadingblue}}{\thechapter.}{10pt}{} 
\sectionfont{\color{logogreen}}  % sets colour of sections
\subsectionfont{\color{logogreen}}  % sets colour of sections

% Title page
\renewcommand{\maketitle}{%
	\newgeometry{margin=0in, paperwidth=8.27in, paperheight=11.69in}
	\thispagestyle{empty}
	\begin{titlepage}
		\vspace*{0.1in}
		
		\begin{raggedright}
			\hspace*{\fill}
			\includegraphics[width=2.0in]{report-assets/logo-full-medium.png}
			\hspace*{0.3in}
		\end{raggedright}
		
		\vspace*{0.7in}
		
		% Document title
		\begin{center}
			\covertitlefont{\project}
			
			\coversubtitlefont{\@title}
		\end{center}
		
		\vspace*{0.8in}
		
		% Document number and client logo
		\hspace*{0.1\textwidth}
		\begin{minipage}[t]{0.5\textwidth}
			\begin{raggedright}
				\coverlabelfont{\docnumber}
				
				\coverlabelfont{Issued on \issueddate}
				
				\coverlabelfont{Revision \revision}
				
			\end{raggedright}
		\end{minipage}%
		\begin{minipage}[t]{0.5\textwidth}
%			\begin{raggedleft}
%				\vspace{-\baselineskip}
%				\hspace*{\fill}
%				\includegraphics[width=2.2in]{report-assets/client-logo.jpg}
%				\hspace*{1.1in}
%			\end{raggedleft}
		\end{minipage}.
		\hspace*{0.1\textwidth}
		
		\vfill
		
		% Bottom graphic
		\begin{minipage}{\textwidth}
			\centering
			\includegraphics[width=0.9\textwidth, keepaspectratio]{report-assets/cover-lower-image.png}
		\end{minipage}
		
		\vspace*{0.2in}
		
		% Disclaimer
		\begin{minipage}{0.7\textwidth}
			\hspace*{0.3in}
			\footerfontbold{%
				CONNECTING YOUR PROJECTS |
			}
			\footerfontnormal{%
				grid-link.com.au
			}
			\vspace{0.5in}
		\end{minipage}
	\end{titlepage}
	\restoregeometry
}

