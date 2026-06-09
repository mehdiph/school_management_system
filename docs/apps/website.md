# Website App Documentation

The `website` application serves as the public-facing landing page and introductory portal for the school management system. It functions as the initial touchpoint for prospective students, parents, and visitors before they authenticate into role-specific panels (such as the teacher or student portals).

---

## 1. System Role & Purpose

The `website` application contains no database models or complex form validators, operating as a lightweight delivery layer for marketing content, school features, and navigational entry points. Its primary roles include:
*   **Brand Presentation:** Highlights school philosophies, technology integration, and teaching staff.
*   **Authentication Portal Linkage:** Features call-to-action (CTA) buttons routing unauthenticated visitors to the secure login application (`accounts:login`).
*   **Navigation Routing:** Connects public links (such as About, Classes, and Blog) in a central header menu.

---

## 2. Views & Routing

### 2.1 URL Routing (`website/urls.py`)
The application routes are registered under the `'website'` namespace:

```python
app_name = 'website'

urlpatterns = [
    path('', views.website, name='website'),
]
```

### 2.2 Controller Logic (`website/views.py`)
The view processes incoming requests with a single functional controller:

```python
def website(request):
    """
    Renders the public landing page.
    """
    return render(request, 'website/index.html')
```

---

## 3. Template Architecture (`website/templates/website/`)

### `index.html`
The page extends the system's global skeleton `base.html` and overrides specific blocks to populate public assets and structural sections.

*   **`navlinks` Block:** Houses the public navigation menu and dynamically renders a "ورود" (Login) button if the client is not currently on the authentication page.
*   **`styles` Block:** Loads the corresponding static stylesheet `index.css`.
*   **`content` Block:** Organizes page content into four structural sections:
    1.  **Hero Banner:** Displays a welcome message, registration CTA, and static student graphics.
    2.  **Why-Us (Features) Grid:** Renders three cards outlining school assets: Robotics ("رباتیک و برنامه نویسی"), Smart Classrooms ("کلاس‌های هوشمند"), and Experienced Teachers ("معلمان مجرب").
    3.  **Active Learning Block:** Displays educational methods alongside a decorative background canvas.
    4.  **Instructors Slider:** Presents a horizontal sliding deck of teacher profiles with associated contact and subject details.
*   **`scripts` Block:** Loads the client-side controller script `index.js` to manage slider animations.

---

## 4. Frontend Styling & Layout (`website/static/website/css/`)

### `index.css`
The page layout relies on a responsive flexbox and CSS grid architecture to handle scaling across multiple device viewports.

*   **Responsive Flex Columns:** The `.hero` section is configured with a column-reverse direction by default on mobile interfaces to stack the textual content above graphics:
    ```css
    .hero {
        display: flex;
        flex-direction: column-reverse;
        align-items: center;
    }
    ```
    On viewports wider than `768px`, this resets to a row distribution to align elements side-by-side.

*   **Interactive Hover Animations:** Feature cards use 3D transition vectors to create subtle elevations when hovered:
    ```css
    .feature-card {
        transition: transform 0.3s;
    }
    .feature-card:hover {
        transform: translateY(-5px);
        box-shadow: 0 8px 25px rgba(0,0,0,0.08);
    }
    ```

*   **Horizontal Slider Mechanics:** The teacher profiles slider maintains a structured width container (`.instructors-grid-wrapper`) set to hide overflow content (`overflow: hidden`). The child grid `.instructors-grid` uses a flex display with no wrapping enabled to allow Javascript-driven horizontal transformations (`transform: translateX(...)`):
    ```css
    .instructors-grid-wrapper {
        overflow: hidden;
        width: 100%;
    }
    .instructors-grid {
        display: flex !important;
        flex-wrap: nowrap !important;
        transition: transform 0.5s cubic-bezier(0.25, 1, 0.5, 1);
    }
    ```

---

## 5. Client-Side Interactivity (`website/static/website/js/`)

### `index.js`
The script initializes the DOM event listeners to handle the horizontal pagination of instructor cards. It calculates the offset widths of individual `.instructor-card` blocks and updates the CSS `transform` parameters on the parent element when the next or previous navigation arrow buttons are clicked.